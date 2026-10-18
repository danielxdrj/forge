export function paginate(items, page, pageSize) {
  const total = items.length;
  const size = pageSize > 0 ? pageSize : total || 1;
  const totalPages = total === 0 ? 0 : Math.ceil(total / size);
  const current = totalPages === 0 ? 0 : Math.min(Math.max(page, 1), totalPages);
  const start = total === 0 ? 0 : (current - 1) * size;
  const pageItems = items.slice(start, start + size);

  return {
    items: pageItems,
    page: current,
    pageSize: size,
    total,
    totalPages,
    from: total === 0 ? 0 : start + 1,
    to: start + pageItems.length,
  };
}
