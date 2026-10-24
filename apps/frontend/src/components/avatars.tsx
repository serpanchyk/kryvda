import { apiClient, type Summary } from "@/api/client";
import photos from "@/lib/entity-photos.json";

type Photo = { src: string; kind: "portrait" | "logo"; author?: string; license?: string; source?: string };
const photoOf = (id: number): Photo | undefined => (photos as Record<string, Photo>)[String(id)];

const tones = ["#5b57e8", "#b04ee8", "#1aa6c4", "#2fb361", "#f08a00", "#3b9cf0", "#e8547a", "#9a7b55"];
const sizes = { sm: "size-8 rounded-[10px] text-[11px]", md: "size-10 rounded-xl text-sm", lg: "size-14 rounded-[18px] text-lg" };

/**
 * A person's portrait or an organisation's emblem from Wikimedia Commons when the registry entry has
 * a verified one; otherwise a coloured squircle with initials. The licence rides on the title.
 */
export function EntityAvatar({ id, name, size = "md" }: { id: number; name: string; size?: keyof typeof sizes }) {
  const photo = photoOf(id);
  if (photo) return <img src={photo.src} alt="" loading="lazy" title={photo.author ? `Фото: ${photo.author}${photo.license ? ` · ${photo.license}` : ""}` : undefined} className={`${sizes[size]} shrink-0 object-cover shadow-[0_0_0_1px_rgb(14_15_18/0.08)] ${photo.kind === "logo" ? "bg-white object-contain p-1" : ""}`} />;
  const initials = name.split(/\s+/).filter((word) => /^[А-ЯІЇЄҐA-Z0-9]/.test(word)).slice(0, 2).map((word) => word[0]).join("") || name.slice(0, 1);
  return <span aria-hidden="true" className={`grid shrink-0 place-items-center font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.35),inset_0_-8px_14px_-10px_rgb(0_0_0/0.25)] ${sizes[size]}`} style={{ background: tones[id % tones.length] }}>{initials}</span>;
}

export function ChannelAvatar({ channel, size = "md" }: { channel: Pick<Summary, "title" | "avatar_url">; size?: "sm" | "md" | "xl" }) {
  const src = apiClient.imageUrl(channel.avatar_url);
  const box = size === "xl" ? "size-24 text-3xl" : size === "sm" ? "size-8 text-sm" : "size-11 text-xl lg:size-12";
  if (src) return <img src={src} alt="" loading="lazy" className={`${box} shrink-0 rounded-full object-cover shadow-[0_0_0_1px_rgb(14_15_18/0.08),0_6px_16px_-8px_rgb(14_15_18/0.35)]`} />;
  return <span aria-hidden="true" className={`${box} grid shrink-0 place-items-center rounded-full bg-[image:var(--ink-gloss)] font-heading font-semibold text-white`}>{channel.title?.slice(0, 1) ?? "К"}</span>;
}
