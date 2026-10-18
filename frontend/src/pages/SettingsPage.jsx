import EmptyState from "../components/EmptyState.jsx";
import PageHeader from "../components/PageHeader.jsx";

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Configurações"
        description="O que já está definido para esta máquina. Preferências da interface ainda não existem."
      />
      <section className="rounded-xl border border-forge-line bg-forge-panel p-4">
        <h2 className="text-base font-semibold">Nesta máquina</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-forge-muted">
          <li>O uso previsto é individual e local.</li>
          <li>A tela não chama a API.</li>
          <li>O endereço da API vem de FORGE_HOST e FORGE_PORT, sem valor padrão, e não é editado aqui.</li>
        </ul>
      </section>
      <section className="rounded-xl border border-forge-line bg-forge-panel p-4">
        <h2 className="mb-3 text-base font-semibold">Preferências</h2>
        <EmptyState>As preferências da interface ficam para uma etapa posterior.</EmptyState>
      </section>
    </div>
  );
}
