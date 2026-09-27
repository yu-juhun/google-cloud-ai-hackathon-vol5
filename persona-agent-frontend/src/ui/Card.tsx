import { HTMLAttributes } from "react";
import "./Card.css";

/** Token-driven surface container — the base building block for any
 * grouped content (avatar preview, result summary, form section). */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={["ui-card", className].filter(Boolean).join(" ")} {...props} />;
}
