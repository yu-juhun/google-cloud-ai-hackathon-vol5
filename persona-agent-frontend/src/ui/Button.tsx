import { ButtonHTMLAttributes } from "react";
import "./Button.css";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary";
}

/** Token-driven button. Restyling the app (swapping tokens.css to a
 * different design-systems/<slug> package) never requires touching this
 * component — only Button.css's var(--token) references matter. */
export function Button({ variant = "primary", className, ...props }: ButtonProps) {
  const variantClass = variant === "primary" ? "ui-button--primary" : "ui-button--secondary";
  return <button className={["ui-button", variantClass, className].filter(Boolean).join(" ")} {...props} />;
}
