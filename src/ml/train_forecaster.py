"""Train the Lochard VIC gas demand forecaster (custom model governed alongside the LLMs).

Replicates and extends the Tableau "R2 – Wk day Wk end" analysis: daily VIC demand (TJ) explained by effective
degree days (EDD), weekday/weekend, month and a demand-decline trend. Two candidates:
  * baseline  – linear regression on EDD per day type (the Tableau R² sheets)
  * champion  – gradient boosted trees on EDD, EDD lag, weekday, month, year index
Logged with MLflow, registered to Unity Catalog (<catalog>.<prefix>ai.vic_gas_demand_forecaster, alias @champion),
then batch-scored to <catalog>.<prefix>ai.vic_demand_forecast (history + 14-day outlook on climatological EDD).
"""
import argparse

import mlflow
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from pyspark.sql import SparkSession
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error, r2_score

FEATURES = ["edd_value", "edd_lag1", "edd_7d_avg", "weekday_num", "is_weekend", "gas_month", "year_idx", "is_holiday"]


def features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("gas_date").copy()
    df["edd_lag1"] = df.edd_value.shift(1).fillna(df.edd_value)
    df["edd_7d_avg"] = df.edd_value.rolling(7, min_periods=1).mean()
    d = pd.to_datetime(df.gas_date)
    df["weekday_num"] = d.dt.weekday
    df["is_weekend"] = (df.weekday_num >= 5).astype(int)
    df["gas_month"] = d.dt.month
    df["year_idx"] = d.dt.year - 2014 + d.dt.dayofyear / 366
    df["is_holiday"] = d.dt.strftime("%m-%d").isin(["01-01", "01-26", "04-25", "12-25", "12-26"]).astype(int)
    return df


class Forecaster(mlflow.pyfunc.PythonModel):
    """Wraps the GBT model; accepts raw daily rows (gas_date, edd_value[, edd_lag1, edd_7d_avg])."""

    def load_context(self, context):
        import joblib
        self.model = joblib.load(context.artifacts["model"])

    def predict(self, context, model_input: pd.DataFrame):
        df = model_input.copy()
        for c in ["edd_lag1", "edd_7d_avg"]:
            if c not in df or df[c].isna().all():
                df[c] = df["edd_value"]
        f = features(df) if "weekday_num" not in df else df
        return pd.DataFrame({"gas_date": f.gas_date.astype(str), "forecast_demand_tj": self.model.predict(f[FEATURES])})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--prefix", required=True)
    a, _ = ap.parse_known_args()
    spark = SparkSession.builder.getOrCreate()
    gold, ai = f"{a.catalog}.{a.prefix}gold", f"{a.catalog}.{a.prefix}ai"
    pdf = spark.sql(f"SELECT gas_date, edd_value, total_gas_used_tj, demand_source FROM {gold}.fact_vic_gas_demand_daily "
                    "WHERE edd_value IS NOT NULL ORDER BY gas_date").toPandas()
    df = features(pdf)
    cutoff = pd.to_datetime(df.gas_date).max() - pd.Timedelta(days=365)
    train, test = df[pd.to_datetime(df.gas_date) <= cutoff], df[pd.to_datetime(df.gas_date) > cutoff]

    from databricks.sdk import WorkspaceClient
    WorkspaceClient().workspace.mkdirs("/Shared/lochard")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment("/Shared/lochard/vic_gas_demand_forecaster")
    with mlflow.start_run(run_name="baseline_edd_linear") as r:
        preds = np.zeros(len(test))
        for wk in (0, 1):
            m = LinearRegression().fit(train.loc[train.is_weekend == wk, ["edd_value"]], train.loc[train.is_weekend == wk, "total_gas_used_tj"])
            idx = (test.is_weekend == wk).values
            preds[idx] = m.predict(test.loc[idx, ["edd_value"]])
            mlflow.log_metric(f"r2_train_{'weekend' if wk else 'weekday'}",
                              r2_score(train.loc[train.is_weekend == wk, "total_gas_used_tj"],
                                       m.predict(train.loc[train.is_weekend == wk, ["edd_value"]])))
        base_mape = mean_absolute_percentage_error(test.total_gas_used_tj, preds)
        mlflow.log_metrics({"mape_holdout": base_mape, "r2_holdout": r2_score(test.total_gas_used_tj, preds)})

    with mlflow.start_run(run_name="champion_gbt") as r:
        model = HistGradientBoostingRegressor(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, random_state=7)
        model.fit(train[FEATURES], train.total_gas_used_tj)
        pred = model.predict(test[FEATURES])
        mape, r2 = mean_absolute_percentage_error(test.total_gas_used_tj, pred), r2_score(test.total_gas_used_tj, pred)
        mlflow.log_params({"model": "HistGradientBoostingRegressor", "features": ",".join(FEATURES),
                           "train_end": str(cutoff.date()), "rows": len(df)})
        mlflow.log_metrics({"mape_holdout": mape, "r2_holdout": r2, "baseline_mape_holdout": base_mape})
        import joblib, tempfile, os
        tmp = os.path.join(tempfile.mkdtemp(), "gbt.joblib")
        joblib.dump(model, tmp)
        example = pdf[["gas_date", "edd_value"]].tail(5).assign(gas_date=lambda x: x.gas_date.astype(str))
        wrapper = Forecaster()
        wrapper.model = model
        sig = infer_signature(example, pd.DataFrame({"gas_date": example.gas_date, "forecast_demand_tj": [500.0] * 5}))
        info = mlflow.pyfunc.log_model(
            name="model", python_model=Forecaster(), artifacts={"model": tmp}, signature=sig, input_example=example,
            pip_requirements=["scikit-learn", "pandas", "numpy", "joblib"])
        print(f"champion MAPE {mape:.3%} (baseline {base_mape:.3%}), R2 {r2:.3f}")

    # Register to Unity Catalog (@champion). The shared FEVM metastore can hit its registered-model quota –
    # in that case keep the MLflow logged model (still versioned + traceable) and score from it.
    name, version = f"{ai}.vic_gas_demand_forecaster", "logged:" + info.model_id
    try:
        mv = mlflow.register_model(info.model_uri, name)
        client = mlflow.MlflowClient()
        version = mv.version
        client.set_registered_model_alias(name, "champion", version)
        client.update_registered_model(name, description=(
            "Lochard VIC gas demand forecaster (TJ/day) from AEMO INT091 EDD and calendar features. Champion = gradient "
            f"boosted trees; holdout MAPE {mape:.2%} vs EDD-linear baseline {base_mape:.2%}. Owner: Lochard data platform. "
            "Intended use: operational demand outlook and agent tool; not for trading decisions."))
        client.set_registered_model_tag(name, "lochard_domain", "market")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: UC registration skipped ({str(e)[:160]}); using MLflow logged model {info.model_id}")

    # batch scoring: last 365 days (actual vs forecast) + 14-day outlook on climatological EDD
    hist = df.tail(365).copy()
    hist["forecast_demand_tj"] = model.predict(hist[FEATURES])
    clim = df.assign(doy=pd.to_datetime(df.gas_date).dt.dayofyear).groupby("doy").edd_value.mean()
    last = pd.to_datetime(df.gas_date).max()
    fut = pd.DataFrame({"gas_date": [(last + pd.Timedelta(days=i)).date() for i in range(1, 15)]})
    fut["edd_value"] = [clim.get(pd.Timestamp(d).dayofyear, clim.mean()) for d in fut.gas_date]
    fut = features(pd.concat([df[["gas_date", "edd_value"]].tail(7), fut])).tail(14)
    fut["forecast_demand_tj"] = model.predict(fut[FEATURES])
    out = pd.concat([hist.assign(kind="backtest"), fut.assign(kind="outlook", total_gas_used_tj=np.nan)])
    out = out[["gas_date", "kind", "edd_value", "total_gas_used_tj", "forecast_demand_tj"]]
    out["model_version"] = str(version)
    sdf = spark.createDataFrame(out.assign(gas_date=pd.to_datetime(out.gas_date)))
    sdf.selectExpr("cast(gas_date as date) gas_date", "kind", "edd_value", "total_gas_used_tj AS actual_demand_tj",
                   "forecast_demand_tj", "model_version", "current_timestamp() AS scored_at") \
       .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{ai}.vic_demand_forecast")
    spark.sql(f"COMMENT ON TABLE {ai}.vic_demand_forecast IS 'Lochard demand forecaster output: 365-day backtest and "
              "14-day outlook (TJ/day), model version tagged'")
    print("scored", len(out), "rows")


if __name__ == "__main__":
    main()
