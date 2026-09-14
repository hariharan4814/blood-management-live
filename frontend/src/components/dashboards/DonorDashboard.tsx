import { Link } from "@tanstack/react-router";
import { CalendarCheck, Droplets, HeartHandshake, HeartPulse, ShieldCheck } from "lucide-react";
import { SectionCard } from "@/components/common/SectionCard";
import { StatCard } from "@/components/common/StatCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardsSkeleton, TableSkeleton, ErrorState } from "@/components/common/StateBlocks";
import { DonorSosAlert } from "@/components/sos/DonorSosAlert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useAsync } from "@/hooks/useAsync";
import { campService } from "@/services/camps/campService";
import { donorService } from "@/services/donors/donorService";
import { requestService } from "@/services/requests/requestService";
import { sosService } from "@/services/sos/sosService";

export function DonorDashboard() {
  const profile = useAsync(() => donorService.getProfile());
  const eligibility = useAsync(() => donorService.checkEligibility());
  const history = useAsync(() => donorService.getDonationHistory());
  const camps = useAsync(() => campService.list());
  const requests = useAsync(() => requestService.list());
  const sos = useAsync(() => sosService.listBroadcasts());

  const activeSos = sos.data?.find((b) => b.status === "ACTIVE");
  const upcoming = camps.data?.filter((c) => c.status !== "COMPLETED") ?? [];
  const activeRequests = requests.data?.filter((r) => r.status === "PENDING" || r.status === "APPROVED") ?? [];

  return (
    <div className="space-y-6">
      {activeSos ? <DonorSosAlert broadcast={activeSos} /> : null}

      {profile.error ? (<ErrorState description={profile.error.message} onRetry={profile.reload} />) : profile.loading || !profile.data ? (
        <CardsSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Blood group" value={profile.data.group} icon={Droplets} hint="Your recorded blood group" />
          <StatCard label="Lifetime donations" value={profile.data.totalDonations ?? "Unknown"} icon={HeartPulse} tone="success" hint="Recorded collections" />
          <StatCard
            label="Eligibility"
            value={profile.data.eligible ? "Eligible" : "On hold"}
            icon={ShieldCheck}
            tone={profile.data.eligible ? "success" : "warning"}
            hint={profile.data.nextEligible}
          />
          <StatCard label="Upcoming camps" value={upcoming.length} icon={CalendarCheck} tone="info" hint="Near your city" />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-2">
        <SectionCard
          title="Eligibility checklist"
          description="Self-declared criteria reviewed before every donation"
          actions={
            <Button asChild size="sm" variant="outline">
              <Link to="/app/profile">Update profile</Link>
            </Button>
          }
        >
          {eligibility.error ? (<ErrorState description={eligibility.error.message} onRetry={eligibility.reload} />) : eligibility.loading || !eligibility.data ? (
            <TableSkeleton rows={4} cols={2} />
          ) : (
            <ul className="space-y-3">
              {eligibility.data.reasons.map((r) => (
                <li key={r.label} className="flex items-center justify-between gap-3 text-sm">
                  <span>{r.label}</span>
                  <StatusBadge status={r.passed ? "PASS" : "FAIL"} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard title="Donation history" description="Your recorded donations" bodyClassName="p-5">
          {history.loading || !history.data ? (
            <TableSkeleton rows={4} cols={3} />
          ) : (
            <ul className="divide-y divide-border">
              {history.data.map((d) => (
                <li key={d.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{d.center}</p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(d.date).toLocaleDateString()} · {d.volumeMl ? `${d.volumeMl} ml` : "Volume not recorded"}
                    </p>
                  </div>
                  <StatusBadge status={d.status === "COMPLETED" ? "COMPLETED" : "REVIEW"} />
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Active blood requests"
        description="Urgent and scheduled clinical requirements in your area"
        actions={
          <Button asChild size="sm" variant="outline">
            <Link to="/app/requests">View all requests</Link>
          </Button>
        }
      >
        {requests.loading || !requests.data ? (
          <CardsSkeleton count={3} />
        ) : activeRequests.length === 0 ? (
          <p className="text-sm text-muted-foreground py-2">
            No active blood requests currently requiring donor responses.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {activeRequests.slice(0, 3).map((r) => (
              <article key={r.id} className="rounded-lg border border-border p-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-bold text-base text-primary">{r.group}</span>
                    <StatusBadge status={r.urgency} />
                  </div>
                  <p className="mt-1 text-sm font-semibold truncate">{r.hospital}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Needed: {r.units} unit(s) · {new Date(r.createdAt).toLocaleDateString()}
                  </p>
                </div>
                <div className="mt-3 pt-3 border-t border-border flex items-center justify-between">
                  <span className="font-mono text-xs text-muted-foreground">{r.id}</span>
                  <Button asChild size="sm">
                    <Link to="/app/requests">
                      <HeartHandshake className="size-3.5 mr-1" /> Respond
                    </Link>
                  </Button>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard
        title="Donation camps near you"
        description="Register in advance to reserve a slot"
        actions={
          <Button asChild size="sm" variant="outline">
            <Link to="/app/camps">View all camps</Link>
          </Button>
        }
      >
        {camps.loading || !camps.data ? (
          <CardsSkeleton count={3} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {upcoming.slice(0, 3).map((c) => (
              <article key={c.id} className="rounded-lg border border-border p-4">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-semibold">{c.name}</h3>
                  <StatusBadge status={c.status} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {new Date(c.date).toLocaleDateString()} · {c.startTime}–{c.endTime} · {c.city}
                </p>
                <div className="mt-3 space-y-1">
                  <Progress value={(c.registered / c.slots) * 100} />
                  <p className="text-xs text-muted-foreground">
                    {c.registered}/{c.slots} slots filled
                  </p>
                </div>
              </article>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}
