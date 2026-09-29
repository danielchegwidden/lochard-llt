import { ReactNode } from "react";
import { Me } from "../api";
import { ROLE_BLURB, ROLE_LABEL } from "../nav";

/** Page title, one-line subtitle and the viewer's role ("Leader view"), with optional controls on the right. */
export default function PageHead({ title, sub, me, right }: { title: string; sub?: ReactNode; me?: Me; right?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1 className="page">{title}</h1>
        {sub && <p className="sub">{sub}</p>}
      </div>
      <div className="page-head-right">
        {me && <span className={`role-pill r-${me.role}`} title={ROLE_BLURB[me.role]}>{ROLE_LABEL[me.role] || me.role} view</span>}
        {right}
      </div>
    </div>
  );
}
