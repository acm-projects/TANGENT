import type { AvailableModel } from "@/api/types";
import { Picker } from "@/ui/library";

/* The model picker the cards' chat and Gent's dock share: each model with its icon and what it's for. */

// by the name the server gives each model (backend core/openrouter.py); an unknown one gets the generic mark
const MODEL_ICON: Record<string, string> = { Lite: "bolt", Balanced: "balance", Heavy: "weight" };
export const modelIcon = (name: string) => MODEL_ICON[name] ?? "neurology";

type ModelSelectProps = {
  models: AvailableModel[];
  value: string;
  onChange(id: string): void;
  "aria-label": string;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  listClassName?: string;
  align?: "start" | "end";
};

export function ModelSelect({ models, value, onChange, loading, disabled, className, listClassName, align, ...rest }: ModelSelectProps) {
  // a card saved with a model this server no longer offers still shows it, by id
  const options = [
    ...(value && !models.some((m) => m.id === value) && !loading ? [{ value, label: value, icon: modelIcon(value) }] : []),
    ...models.map((m) => ({ value: m.id, label: m.name, icon: modelIcon(m.name), description: m.description })),
  ];
  return (
    <Picker
      aria-label={rest["aria-label"]}
      className={className}
      listClassName={listClassName}
      align={align}
      options={options}
      value={value}
      onChange={onChange}
      disabled={disabled || loading || models.length === 0}
      placeholder={loading ? "Loading models…" : "No models available"}
    />
  );
}
