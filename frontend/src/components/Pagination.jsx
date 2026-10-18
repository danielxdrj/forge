import Button from "./Button.jsx";

export default function Pagination({ page, totalPages, from, to, total, onPageChange }) {
  if (total === 0) return null;

  return (
    <nav aria-label="Paginação" className="flex flex-wrap items-center justify-between gap-3 text-sm">
      <p className="text-forge-muted">
        {from}–{to} de {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Anterior
        </Button>
        <p>
          Página {page} de {totalPages}
        </p>
        <Button
          variant="ghost"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Próxima
        </Button>
      </div>
    </nav>
  );
}
