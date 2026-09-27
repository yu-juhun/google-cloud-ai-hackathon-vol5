import { AvatarTemplateCatalog } from "../ws/PersonaSocket";
import "./TemplatePicker.css";

const GENDER_LABELS: Record<string, string> = { male: "男性", female: "女性" };

export interface TemplatePickerProps {
  catalog: AvatarTemplateCatalog;
  gender: string;
  onGenderChange: (gender: string) => void;
  templateId: string;
  onTemplateChange: (templateId: string) => void;
}

/** Real-thumbnail grid picker for the YouCam avatar style, grouped by
 * gender then category — replaces a text-only <select> because a style
 * choice ("Manga Mood" vs "Yearbook") is fundamentally a visual decision.
 * Requires an explicit gender before any style is selectable, so a photo
 * upload can never silently fall through to a hardcoded gendered
 * default. */
export function TemplatePicker({ catalog, gender, onGenderChange, templateId, onTemplateChange }: TemplatePickerProps) {
  const genders = Object.keys(catalog);
  const categories = gender ? catalog[gender] ?? {} : {};

  return (
    <div className="template-picker">
      <div className="template-picker__genders" role="radiogroup" aria-label="性別">
        {genders.map((g) => (
          <button
            key={g}
            type="button"
            role="radio"
            aria-checked={gender === g}
            className={`template-picker__gender ${gender === g ? "template-picker__gender--selected" : ""}`}
            onClick={() => onGenderChange(g)}
          >
            {GENDER_LABELS[g] ?? g}
          </button>
        ))}
      </div>

      {!gender && <p className="template-picker__hint">性別を選択すると、アバターのスタイルを選べます</p>}

      {gender &&
        Object.entries(categories).map(([category, entries]) => (
          <fieldset key={category} className="template-picker__category">
            <legend>{category}</legend>
            <div className="template-picker__grid">
              {entries.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  role="radio"
                  aria-checked={templateId === entry.id}
                  className={`template-picker__option ${templateId === entry.id ? "template-picker__option--selected" : ""}`}
                  onClick={() => onTemplateChange(entry.id)}
                >
                  {entry.thumb && <img src={entry.thumb} alt={entry.title} loading="lazy" />}
                  <span>{entry.title}</span>
                </button>
              ))}
            </div>
          </fieldset>
        ))}
    </div>
  );
}
