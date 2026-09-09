export function codePointSpan(text, start, end) {
  return {
    start: Array.from(text.slice(0, start)).length,
    end: Array.from(text.slice(0, end)).length,
  };
}
export function spanText(text, span) {
  return Array.from(text).slice(span.start, span.end).join("");
}
