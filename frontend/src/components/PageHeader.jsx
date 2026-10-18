export default function PageHeader({ title, description, action }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold">{title}</h1>
        <p className="mt-1 max-w-2xl text-sm text-forge-muted">{description}</p>
      </div>
      {action}
    </header>
  );
}
