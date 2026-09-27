import { SelectHTMLAttributes } from "react";
import "./Select.css";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "children"> {
  label: string;
  options: SelectOption[];
}

/** Labeled select — the implicit `<label><span/><select/></label>` wrapping
 * makes it accessible via getByLabelText without any id/htmlFor wiring. */
export function Select({ label, options, className, ...props }: SelectProps) {
  return (
    <label className="ui-select">
      <span className="ui-select__label">{label}</span>
      <select className={["ui-select__input", className].filter(Boolean).join(" ")} {...props}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
