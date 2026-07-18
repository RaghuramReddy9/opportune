export function toggleCappedSelection(
  current: string[],
  value: string,
  maxSelections: number,
): string[] {
  if (current.includes(value)) return current.filter((item) => item !== value);
  if (current.length >= maxSelections) return current;
  return [...current, value];
}

export function normalizeWorkFocuses(value: string | string[] | undefined): string[] {
  const values = Array.isArray(value) ? value : value ? [value] : [];
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))].slice(0, 3);
}

export function parseLocationDraft(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean);
}
