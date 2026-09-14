import { useState } from "react";
import { Clock, MapPin, Siren } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { MapPlaceholder } from "@/components/common/MapPlaceholder";
import { StatusBadge } from "@/components/common/StatusBadge";
import { sosService } from "@/services/sos/sosService";
import type { SosBroadcast } from "@/lib/types";

export function DonorSosAlert({ broadcast }: { broadcast: SosBroadcast }) {
  const [answer, setAnswer] = useState<"AVAILABLE" | "UNAVAILABLE" | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const respond = async (value: "AVAILABLE" | "UNAVAILABLE") => {
    setPending(true);
    try {
      await sosService.respond(broadcast.id, value);
      setAnswer(value);
      toast.success(
        value === "AVAILABLE"
          ? "Thank you — the blood bank will contact you shortly."
          : "Response recorded. You won't be contacted for this alert.",
      );
    } finally {
      setPending(false);
      setConfirmOpen(false);
    }
  };

  return (
    <section className="card-surface overflow-hidden border-destructive/30">
      <div className="flex flex-wrap items-center gap-3 border-b border-destructive/25 bg-destructive/8 px-5 py-4">
        <span className="grid size-9 place-items-center rounded-lg bg-destructive/15 text-destructive">
          <Siren className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 className="font-semibold tracking-tight">Emergency SOS alert</h2>
          <p className="text-xs text-muted-foreground">
            Broadcast {broadcast.id} · issued by {broadcast.hospital}
          </p>
        </div>
        <div className="ml-auto flex gap-2">
          <StatusBadge status={broadcast.urgency} />
          <StatusBadge status={broadcast.status} />
        </div>
      </div>

      <div className="grid gap-5 p-5 lg:grid-cols-[1fr_1fr]">
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <dt className="text-muted-foreground">Blood group needed</dt>
              <dd className="text-2xl font-bold text-primary">{broadcast.group}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Units required</dt>
              <dd className="text-2xl font-semibold">{broadcast.units}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Location</dt>
              <dd className="flex items-center gap-1.5 font-medium">
                <MapPin className="size-4 text-muted-foreground" /> {broadcast.city}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Search radius</dt>
              <dd className="flex items-center gap-1.5 font-medium">
                <Clock className="size-4 text-muted-foreground" /> Within {broadcast.radiusKm ? `${broadcast.radiusKm} km` : "emergency radius"}
              </dd>
            </div>
          </dl>

          {answer ? (
            <div className="rounded-md border border-border bg-muted/50 px-4 py-3 text-sm">
              You responded: <StatusBadge status={answer} className="ml-1" />
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setConfirmOpen(true)} disabled={pending}>
                I'm Available
              </Button>
              <Button
                variant="outline"
                onClick={() => respond("UNAVAILABLE")}
                disabled={pending}
              >
                Not Available
              </Button>
            </div>
          )}
        </div>

        <MapPlaceholder
          radiusKm={broadcast.radiusKm}
          centerLabel={broadcast.hospital}
          markerCount={broadcast.notified}
          height="h-56"
        />
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm your availability"
        description={`You are confirming you can donate ${broadcast.group} blood at ${broadcast.hospital} today. The blood bank will call you on your registered number.`}
        confirmLabel="Yes, I can donate"
        onConfirm={() => respond("AVAILABLE")}
      />
    </section>
  );
}
