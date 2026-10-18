export default function EmptyState({ title, children }) {
  return (
    <div className="rounded-lg border border-dashed border-forge-line px-4 py-8 text-center">
      {title ? <p className="font-medium">{title}</p> : null}
      <p className={`text-sm text-forge-muted ${title ? "mt-1" : ""}`}>{children}</p>
    </div>
  );
}
