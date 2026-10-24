import { uk } from "date-fns/locale";
import type { DateRange } from "react-day-picker";

import { Calendar } from "@/components/ui/calendar";

/** The custom-range calendar, split into its own chunk: it loads only when the period popover opens. */
export default function RangeCalendar({ selected, onSelect }: { selected?: DateRange; onSelect: (range?: DateRange) => void }) {
  return <Calendar mode="range" selected={selected} onSelect={onSelect} locale={uk} numberOfMonths={1} />;
}
