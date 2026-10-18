import { useMemo, useState } from "react";
import EmptyState from "../components/EmptyState.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Pagination from "../components/Pagination.jsx";
import { IconSearch } from "../components/icons.jsx";
import { paginate } from "../lib/pagination.js";

const entries = [];
const pageSize = 20;

export default function LocalLogPage() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return entries;
    return entries.filter((entry) => String(entry.text ?? "").toLowerCase().includes(term));
  }, [query]);

  const listing = paginate(filtered, page, pageSize);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Log local"
        description="As entradas de log aparecem aqui quando a API as entregar. Esta tela não lê arquivos do computador."
      />
      <section className="flex flex-col gap-3 rounded-xl border border-forge-line bg-forge-panel p-4">
        <div className="relative">
          <IconSearch className="pointer-events-none absolute top-2.5 left-3 size-4 text-forge-muted" />
          <label htmlFor="log-search" className="sr-only">
            Buscar no log
          </label>
          <input
            id="log-search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(1);
            }}
            placeholder="Buscar no texto do log"
            className="w-full rounded-lg border border-forge-line bg-forge-bg py-2 pr-3 pl-9 text-sm"
          />
        </div>
        {listing.total === 0 ? (
          <EmptyState>Nenhuma entrada de log para mostrar.</EmptyState>
        ) : (
          <pre className="overflow-auto rounded-lg border border-forge-line bg-forge-bg p-3 text-sm whitespace-pre-wrap">
            {listing.items.map((entry) => entry.text).join("\n")}
          </pre>
        )}
        <Pagination
          page={listing.page}
          totalPages={listing.totalPages}
          from={listing.from}
          to={listing.to}
          total={listing.total}
          onPageChange={setPage}
        />
      </section>
    </div>
  );
}
