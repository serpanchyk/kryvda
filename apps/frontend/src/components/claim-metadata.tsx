import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import type {
  EpistemicStatus,
  RhetoricLabel,
  SourceKind,
  Stance,
} from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  epistemicLabels,
  formatDateTime,
  rhetoricLabels,
  sourceLabels,
  stanceLabels,
} from "@/lib/editorial";

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
    "font-semibold hover:text-negative focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-negative";
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
    <Badge variant="outline" className={cn("rounded-none", className)}>
      {children}
    </Badge>
  );
  if (action?.href)
    return (
      <Link
        to={action.href}
        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-negative"
      >
        {badge}
      </Link>
    );
  if (action?.onClick)
    return (
      <button
        type="button"
        onClick={action.onClick}
        className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-negative"
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
      ? "border-negative text-negative"
      : stance === "позитивне"
        ? "border-positive text-positive"
        : "border-neutral text-muted-foreground";
  return (
    <MetadataBadge action={action} className={className}>
      {stanceLabels[stance]}
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
    <MetadataBadge action={action} className="border-ink/50 text-ink">
      {epistemicLabels[status]}
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
          className="border-rule text-muted-foreground"
        >
          {rhetoricLabels[label]}
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
}: {
  data: ClaimMetadataData;
  actions?: ClaimMetadataActions;
}) {
  return (
    <div className="grid gap-3 border-y border-rule py-3 text-sm sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-start">
      <div>
        <p className="eyebrow text-muted-foreground">Опубліковано</p>
        <MetadataValue action={actions?.channel}>
          {data.channel_title}
        </MetadataValue>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {formatDateTime(data.published_at)}
        </p>
      </div>
      <div>
        <p className="eyebrow text-muted-foreground">Ціль</p>
        <MetadataValue action={actions?.entity}>
          {data.entity_name}
        </MetadataValue>
      </div>
      <AttributionSource data={data} action={actions?.source} />
      <div className="flex flex-wrap items-center gap-2 sm:col-span-2 xl:col-span-3">
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
