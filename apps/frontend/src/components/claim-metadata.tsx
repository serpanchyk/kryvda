import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import type {
  EpistemicStatus,
  RhetoricLabel,
  SourceKind,
  Stance,
} from "@/api/client";
import { TermLabel } from "@/components/editorial";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  formatDateTime,
  sourceLabels,
} from "@/lib/editorial";
import { termOf } from "@/lib/glossary";

export type MetadataAction = { href?: string; onClick?: () => void };
export type ClaimMetadataData = {
  published_at: string;
  channel_id: number;
  channel_title: string;
  entity_id?: number;
  entity_name: string;
  stance: Stance;
  epistemic_status: EpistemicStatus;
  rhetoric: RhetoricLabel[];
  source_kind: SourceKind;
  source_entity_id?: number | null;
  source_entity_name?: string | null;
};
export type ClaimMetadataActions = {
  channel?: MetadataAction;
  entity?: MetadataAction;
  stance?: MetadataAction;
  epistemic?: MetadataAction;
  rhetoric?: (label: RhetoricLabel) => MetadataAction | undefined;
  source?: MetadataAction;
};

function MetadataValue({
  children,
  action,
}: {
  children: ReactNode;
  action?: MetadataAction;
}) {
  const className =
    "rounded font-semibold transition-colors hover:text-negative";
  if (action?.href)
    return (
      <Link to={action.href} className={className}>
        {children}
      </Link>
    );
  if (action?.onClick)
    return (
      <button type="button" onClick={action.onClick} className={className}>
        {children}
      </button>
    );
  return <span className="font-semibold">{children}</span>;
}

function MetadataBadge({
  children,
  action,
  className,
}: {
  children: ReactNode;
  action?: MetadataAction;
  className: string;
}) {
  const badge = (
    <Badge variant="outline" className={cn("h-6 rounded-full border-transparent px-2.5 text-xs font-medium transition-colors", className)}>
      {children}
    </Badge>
  );
  if (action?.href)
    return (
      <Link
        to={action.href}
        className="rounded-full"
      >
        {badge}
      </Link>
    );
  if (action?.onClick)
    return (
      <button
        type="button"
        onClick={action.onClick}
        className="rounded-full"
      >
        {badge}
      </button>
    );
  return badge;
}

export function StanceBadge({
  stance,
  action,
}: {
  stance: Stance;
  action?: MetadataAction;
}) {
  const className =
    stance === "негативне"
      ? "bg-negative/10 text-negative hover:bg-negative/15"
      : stance === "позитивне"
        ? "bg-positive/10 text-positive hover:bg-positive/15"
        : "bg-foreground/[0.06] text-muted-foreground";
  return (
    <MetadataBadge action={action} className={className}>
      <TermLabel term={termOf("stance", stance)} />
    </MetadataBadge>
  );
}

export function EpistemicBadge({
  status,
  action,
}: {
  status: EpistemicStatus;
  action?: MetadataAction;
}) {
  return (
    <MetadataBadge action={action} className="bg-foreground/[0.06] text-foreground hover:bg-foreground/10">
      <TermLabel term={termOf("epistemic", status)} />
    </MetadataBadge>
  );
}

export function RhetoricBadges({
  rhetoric,
  action,
}: {
  rhetoric: RhetoricLabel[];
  action?: ClaimMetadataActions["rhetoric"];
}) {
  if (rhetoric.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="eyebrow text-muted-foreground">Риторика</span>
      {rhetoric.map((label) => (
        <MetadataBadge
          key={label}
          action={action?.(label)}
          className="bg-white/60 text-muted-foreground shadow-[inset_0_0_0_1px_rgb(14_15_18/0.08)] hover:bg-white"
        >
          <TermLabel term={termOf("rhetoric", label)} />
        </MetadataBadge>
      ))}
    </div>
  );
}

export function AttributionSource({
  data,
  action,
}: {
  data: Pick<
    ClaimMetadataData,
    "source_kind" | "source_entity_id" | "source_entity_name"
  >;
  action?: MetadataAction;
}) {
  const sourceName =
    data.source_kind === "named_entity" && data.source_entity_name
      ? data.source_entity_name
      : sourceLabels[data.source_kind];
  const canFilter =
    data.source_kind === "named_entity" && data.source_entity_id != null;
  return (
    <div className="min-w-0">
      <p className="eyebrow text-muted-foreground">Джерело твердження</p>
      <MetadataValue action={canFilter ? action : undefined}>
        {sourceName}
      </MetadataValue>
      <p className="mt-0.5 text-xs text-muted-foreground">
        Тип: {sourceLabels[data.source_kind]}
      </p>
    </div>
  );
}

export function ClaimMetadata({
  data,
  actions,
  hidePublication = false,
  className,
}: {
  data: ClaimMetadataData;
  actions?: ClaimMetadataActions;
  /** Omit channel and date where the surrounding page already states them. */
  hidePublication?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("grid grid-cols-2 gap-x-4 gap-y-3 text-sm xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-start", className)}>
      {hidePublication ? null : <div>
        <p className="eyebrow text-muted-foreground">Опубліковано</p>
        <MetadataValue action={actions?.channel}>
          {data.channel_title}
        </MetadataValue>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatDateTime(data.published_at)}
        </p>
      </div>}
      <div>
        <p className="eyebrow text-muted-foreground">Ціль</p>
        <MetadataValue action={actions?.entity}>
          {data.entity_name}
        </MetadataValue>
      </div>
      <AttributionSource data={data} action={actions?.source} />
      <div className="col-span-2 flex flex-wrap items-center gap-2 xl:col-span-3">
        <span className="eyebrow text-muted-foreground">Статус</span>
        <EpistemicBadge
          status={data.epistemic_status}
          action={actions?.epistemic}
        />
        <span className="eyebrow ml-1 text-muted-foreground">Позиція</span>
        <StanceBadge stance={data.stance} action={actions?.stance} />
        <RhetoricBadges rhetoric={data.rhetoric} action={actions?.rhetoric} />
      </div>
    </div>
  );
}
