export function formatMoney(value: string | number, currency = "BRL") {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency }).format(Number(value));
}

export function formatDate(value: string | Date) {
  return new Intl.DateTimeFormat("pt-BR").format(value instanceof Date ? value : new Date(value));
}
