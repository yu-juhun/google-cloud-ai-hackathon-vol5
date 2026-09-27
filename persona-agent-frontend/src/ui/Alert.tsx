import { HTMLAttributes } from "react";
import "./Alert.css";

export type AlertTone = "danger" | "success" | "warn";

export interface AlertProps extends HTMLAttributes<HTMLParagraphElement> {
  tone?: AlertTone;
}

/** role="alert" by default — screen readers announce it as soon as it
 * mounts, which is exactly what an error/status banner needs. */
export function Alert({ tone = "danger", role = "alert", className, ...props }: AlertProps) {
  return (
    <p role={role} className={["ui-alert", `ui-alert--${tone}`, className].filter(Boolean).join(" ")} {...props} />
  );
}
