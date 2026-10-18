export default function TextField({
  id,
  label,
  hint,
  multiline = false,
  className = "",
  ...props
}) {
  const fieldClass =
    "w-full rounded-lg border border-forge-line bg-forge-bg px-3 py-2 text-sm text-forge-text placeholder:text-forge-muted";
  const Field = multiline ? "textarea" : "input";

  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1 block text-sm text-forge-muted">
        {label}
      </label>
      <Field id={id} className={fieldClass} {...props} />
      {hint ? <p className="mt-1 text-xs text-forge-muted">{hint}</p> : null}
    </div>
  );
}
