import { useEffect, useMemo, useState } from "react";
import { createFileRoute, useLocation } from "@tanstack/react-router";
import {
  Building2,
  CheckCircle2,
  Droplet,
  ExternalLink,
  Filter,
  Hospital as HospitalIcon,
  Info,
  Loader2,
  LocateFixed,
  Lock,
  MapPin,
  Navigation,
  Phone,
  RefreshCw,
  Search,
  Send,
  Star,
  User,
  Users,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { EmptyState } from "@/components/common/StateBlocks";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { LeafletMap, type MapMarkerItem } from "@/components/map/LeafletMap";
import { DonorContactModal } from "@/components/donors/DonorContactModal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { BLOOD_GROUPS } from "@/lib/types";
import { useAuth } from "@/providers/AuthProvider";
import {
  nearbyService,
  type NearbyBloodBank,
  type NearbyDonor,
  type NearbyHospital,
  type NearbySearchParams,
  type NearbySearchResponse,
} from "@/services/nearby/nearbyService";
import { profileService } from "@/services/profile/profileService";

export const Route = createFileRoute("/app/map")({
  head: () => ({
    meta: [
      { title: "Map & Nearby Resources — Blood Management System" },
      {
        name: "description",
        content:
          "Locate nearby blood banks, registered partner hospitals and compatible donors using OpenStreetMap and Leaflet.",
      },
      { property: "og:title", content: "Map & Nearby Resources — Blood Management System" },
      { property: "og:description", content: "Locate nearby blood banks, all registered hospitals and donors." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: NearbyMapPage,
});

const DEFAULT_CENTER: [number, number] = [13.0827, 80.2707]; // Chennai default

function NearbyMapPage() {
  const location = useLocation();
  const { user } = useAuth();

  const searchParams = useMemo(() => {
    const params = new URLSearchParams(location.search);
    const latStr = params.get("lat");
    const lngStr = params.get("lng");
    const radiusStr = params.get("radius");
    const bloodGroupStr = params.get("blood_group");
    const typeStr = params.get("type");

    return {
      lat: latStr ? parseFloat(latStr) : undefined,
      lng: lngStr ? parseFloat(lngStr) : undefined,
      radius: radiusStr ? parseInt(radiusStr, 10) : undefined,
      blood_group: bloodGroupStr || undefined,
      type: typeStr || undefined,
    };
  }, [location.search]);

  const [center, setCenter] = useState<[number, number]>(() => {
    if (searchParams.lat && searchParams.lng) {
      return [searchParams.lat, searchParams.lng];
    }
    return DEFAULT_CENTER;
  });

  const [radius, setRadius] = useState<number>(() => searchParams.radius || 25);
  const [bloodGroup, setBloodGroup] = useState<string>(() => searchParams.blood_group || "ALL");

  // All authenticated users can discover nearby donors
  const [includeDonors, setIncludeDonors] = useState<boolean>(true);
  const [includeHospitals, setIncludeHospitals] = useState<boolean>(true);
  const [includeBloodBanks, setIncludeBloodBanks] = useState<boolean>(true);
  const [allHospitalsMode, setAllHospitalsMode] = useState<boolean>(false);

  const [searchFilter, setSearchFilter] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [geolocating, setGeolocating] = useState<boolean>(false);
  const [data, setData] = useState<NearbySearchResponse | null>(null);
  const [focusedMarkerId, setFocusedMarkerId] = useState<string | number | null>(null);
  const [userSavedLocationLoaded, setUserSavedLocationLoaded] = useState<boolean>(false);

  // Contact Modal State
  const [contactModalOpen, setContactModalOpen] = useState<boolean>(false);
  const [selectedDonorForContact, setSelectedDonorForContact] = useState<{ id: number; bloodGroup: string } | null>(null);

  // Load user saved location on initial mount if not provided via search URL
  useEffect(() => {
    if (searchParams.lat && searchParams.lng) {
      setUserSavedLocationLoaded(true);
      return;
    }

    profileService
      .getProfile()
      .then((p) => {
        if (typeof p.latitude === "number" && typeof p.longitude === "number") {
          setCenter([p.latitude, p.longitude]);
        }
      })
      .catch(() => {})
      .finally(() => {
        setUserSavedLocationLoaded(true);
      });
  }, []);

  const fetchNearby = async () => {
    setLoading(true);
    try {
      const typesList: string[] = [];
      if (includeDonors) typesList.push("donors");
      if (includeHospitals) typesList.push("hospitals");
      if (includeBloodBanks) typesList.push("blood_banks");

      const queryParams: NearbySearchParams = {
        lat: center[0],
        lng: center[1],
        radius,
        type: typesList.length > 0 ? typesList.join(",") : "none",
        all_hospitals: allHospitalsMode,
      };
      if (bloodGroup !== "ALL") {
        queryParams.blood_group = bloodGroup;
      }

      const res = await nearbyService.searchNearby(queryParams);
      setData(res);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load resources.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userSavedLocationLoaded) {
      fetchNearby();
    }
  }, [center, radius, bloodGroup, includeDonors, includeHospitals, includeBloodBanks, allHospitalsMode, userSavedLocationLoaded]);

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      toast.error("Browser geolocation is not supported on this device.");
      return;
    }

    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCenter([pos.coords.latitude, pos.coords.longitude]);
        setGeolocating(false);
        toast.success("Location set to your current GPS position.");
      },
      () => {
        setGeolocating(false);
        toast.error("Location permission denied or unavailable.");
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const handleOpenContactModal = (donorId: number, bloodGroupStr: string) => {
    setSelectedDonorForContact({ id: donorId, bloodGroup: bloodGroupStr });
    setContactModalOpen(true);
  };

  // Prepare map markers
  const markers: MapMarkerItem[] = useMemo(() => {
    const list: MapMarkerItem[] = [];

    // Search Center Pin
    list.push({
      id: "search-center",
      type: "user",
      title: "Search Center",
      latitude: center[0],
      longitude: center[1],
      details: {
        address: "Current search anchor",
      },
    });

    if (data?.results) {
      // Donors (Sanitized discovery with fuzzed coordinates)
      if (includeDonors && data.results.donors) {
        data.results.donors.forEach((d) => {
          list.push({
            id: d.id,
            type: "donor",
            title: `Donor #${d.donor_id} (${d.blood_group})`,
            latitude: d.approximate_latitude,
            longitude: d.approximate_longitude,
            distanceKm: d.distance_km,
            details: {
              bloodGroup: d.blood_group,
              isEligible: d.is_eligible,
              address: "Approximate location (~1.1 km resolution). Contact details protected.",
            },
            onClick: () => setFocusedMarkerId(d.id),
          });
        });
      }

      // Hospitals (All registered or nearby)
      if (includeHospitals && data.results.hospitals) {
        data.results.hospitals.forEach((h) => {
          list.push({
            id: `hosp-${h.id}`,
            type: "hospital",
            title: h.name,
            latitude: h.latitude,
            longitude: h.longitude,
            distanceKm: h.distance_km,
            details: {
              address: h.address,
              city: h.city,
              contactNumber: h.contact_number,
              beds: h.beds,
              rating: h.rating,
              reviewCount: h.review_count,
            },
            onClick: () => setFocusedMarkerId(`hosp-${h.id}`),
          });
        });
      }

      // Blood Banks
      if (includeBloodBanks && data.results.blood_banks) {
        data.results.blood_banks.forEach((b) => {
          list.push({
            id: `bank-${b.id}`,
            type: "blood_bank",
            title: b.name,
            latitude: b.latitude,
            longitude: b.longitude,
            distanceKm: b.distance_km,
            details: {
              address: b.address,
              city: b.city,
              contactNumber: b.contact_number,
              capacity: b.capacity,
              rating: b.rating,
              reviewCount: b.review_count,
            },
            onClick: () => setFocusedMarkerId(`bank-${b.id}`),
          });
        });
      }
    }

    return list;
  }, [center, data, includeDonors, includeHospitals, includeBloodBanks]);

  // Filtered lists for sidebar
  const filteredDonors = useMemo(() => {
    if (!data?.results?.donors) return [];
    if (!searchFilter.trim()) return data.results.donors;
    const term = searchFilter.toLowerCase();
    return data.results.donors.filter(
      (d) =>
        d.blood_group.toLowerCase().includes(term) ||
        `donor #${d.donor_id}`.toLowerCase().includes(term)
    );
  }, [data?.results?.donors, searchFilter]);

  const filteredHospitals = useMemo(() => {
    if (!data?.results?.hospitals) return [];
    if (!searchFilter.trim()) return data.results.hospitals;
    const term = searchFilter.toLowerCase();
    return data.results.hospitals.filter(
      (h) =>
        h.name.toLowerCase().includes(term) ||
        h.city.toLowerCase().includes(term) ||
        h.state.toLowerCase().includes(term)
    );
  }, [data?.results?.hospitals, searchFilter]);

  const filteredBloodBanks = useMemo(() => {
    if (!data?.results?.blood_banks) return [];
    if (!searchFilter.trim()) return data.results.blood_banks;
    const term = searchFilter.toLowerCase();
    return data.results.blood_banks.filter(
      (b) =>
        b.name.toLowerCase().includes(term) ||
        b.city.toLowerCase().includes(term) ||
        b.state.toLowerCase().includes(term)
    );
  }, [data?.results?.blood_banks, searchFilter]);

  return (
    <DashboardLayout title="Map & Resources">
      <PageHeader
        title="Interactive Map & Facilities"
        description="Explore nearby donors, all registered partner hospitals, and blood banks on OpenStreetMap with Leaflet."
      />

      {/* Control Bar */}
      <SectionCard className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={handleUseCurrentLocation}
              disabled={geolocating}
            >
              {geolocating ? (
                <Loader2 className="mr-2 size-4 animate-spin" />
              ) : (
                <LocateFixed className="mr-2 size-4 text-primary" />
              )}
              Use My Location
            </Button>

            {/* Radius Selector */}
            <div className="flex items-center gap-2">
              <Label htmlFor="radius-select" className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
                Radius:
              </Label>
              <Select value={String(radius)} onValueChange={(val) => setRadius(Number(val))}>
                <SelectTrigger id="radius-select" className="w-28 h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">5 km</SelectItem>
                  <SelectItem value="10">10 km</SelectItem>
                  <SelectItem value="25">25 km</SelectItem>
                  <SelectItem value="50">50 km</SelectItem>
                  <SelectItem value="100">100 km</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Blood Group Filter */}
            <div className="flex items-center gap-2">
              <Label htmlFor="bg-select" className="text-xs font-semibold text-muted-foreground whitespace-nowrap">
                Blood Group:
              </Label>
              <Select value={bloodGroup} onValueChange={setBloodGroup}>
                <SelectTrigger id="bg-select" className="w-24 h-8 text-xs font-bold text-primary">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All</SelectItem>
                  {BLOOD_GROUPS.map((g) => (
                    <SelectItem key={g} value={g}>
                      {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* All Hospitals Toggle */}
            <div className="flex items-center gap-2 pl-2 border-l border-border">
              <Switch
                id="all-hosp-toggle"
                checked={allHospitalsMode}
                onCheckedChange={setAllHospitalsMode}
              />
              <Label htmlFor="all-hosp-toggle" className="text-xs font-semibold cursor-pointer">
                All Registered Hospitals
              </Label>
            </div>
          </div>

          {/* Refresh Button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchNearby}
            disabled={loading}
            className="text-xs"
          >
            <RefreshCw className={`mr-1.5 size-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {/* Entity Type Checkbox Filters */}
        <div className="flex flex-wrap items-center justify-between gap-4 mt-4 pt-4 border-t border-border">
          <div className="flex flex-wrap items-center gap-6">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Filter className="size-3.5" /> Entities:
            </span>

            <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
              <Checkbox
                checked={includeHospitals}
                onCheckedChange={(checked) => setIncludeHospitals(Boolean(checked))}
              />
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-blue-600" />
                Hospitals ({data?.results.hospitals.length ?? 0})
              </span>
            </label>

            <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
              <Checkbox
                checked={includeBloodBanks}
                onCheckedChange={(checked) => setIncludeBloodBanks(Boolean(checked))}
              />
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-emerald-600" />
                Blood Banks ({data?.results.blood_banks.length ?? 0})
              </span>
            </label>

            <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
              <Checkbox
                checked={includeDonors}
                onCheckedChange={(checked) => setIncludeDonors(Boolean(checked))}
              />
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-rose-600" />
                Nearby Donors ({data?.results.donors.length ?? 0})
              </span>
            </label>
          </div>

          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
            <Input
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Search in results..."
              className="h-8 text-xs pl-8"
            />
          </div>
        </div>
      </SectionCard>

      {/* Main Map and Results Layout */}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.8fr)_minmax(0,1.2fr)]">
        {/* Map Panel */}
        <div className="space-y-4">
          <LeafletMap
            center={center}
            zoom={12}
            markers={markers}
            radiusKm={allHospitalsMode ? null : radius}
            height="h-[540px]"
            focusedMarkerId={focusedMarkerId}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground px-1">
            <div className="flex items-center gap-4">
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-indigo-600 ring-2 ring-indigo-300" />
                Search Center
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-blue-600" />
                Hospital
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-emerald-600" />
                Blood Bank
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="size-2.5 rounded-full bg-rose-600" />
                Donor (~1.1km approx)
              </span>
            </div>
            <span>{allHospitalsMode ? "Showing all registered hospitals" : `${radius} km radius search`}</span>
          </div>
        </div>

        {/* Results Sidebar Panel */}
        <div className="space-y-4 max-h-[580px] overflow-y-auto pr-1">
          {loading ? (
            <div className="rounded-xl border border-border bg-card p-12 text-center">
              <Loader2 className="size-8 animate-spin text-primary mx-auto mb-3" />
              <p className="text-sm font-medium">Scanning coordinates...</p>
              <p className="text-xs text-muted-foreground mt-1">Retrieving verified facilities and nearby donors</p>
            </div>
          ) : data?.total_count === 0 ? (
            <div className="rounded-xl border border-border bg-card p-8 text-center">
              <MapPin className="size-10 text-muted-foreground mx-auto mb-3 opacity-40" />
              <h3 className="font-semibold text-sm">No resources found</h3>
              <p className="text-xs text-muted-foreground mt-1 mb-4">
                Try expanding your search radius, toggling "All Registered Hospitals", or adjusting filters.
              </p>
              <div className="flex justify-center gap-2">
                <Button size="sm" variant="outline" onClick={() => setRadius(50)}>
                  Expand to 50 km
                </Button>
                <Button size="sm" onClick={() => setAllHospitalsMode(true)}>
                  Show All Hospitals
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Hospitals List */}
              {includeHospitals &&
                filteredHospitals.map((h) => (
                  <div
                    key={`hosp-${h.id}`}
                    onClick={() => setFocusedMarkerId(`hosp-${h.id}`)}
                    className={`rounded-xl border p-4 bg-card cursor-pointer transition-all hover:border-blue-500 hover:shadow-sm ${
                      focusedMarkerId === `hosp-${h.id}` ? "border-blue-600 ring-2 ring-blue-500/20" : "border-border"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="flex size-7 items-center justify-center rounded-lg bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400">
                          <HospitalIcon className="size-4" />
                        </span>
                        <div>
                          <h4 className="font-bold text-sm leading-tight text-foreground">{h.name}</h4>
                          <p className="text-xs text-muted-foreground">{h.city}, {h.state}</p>
                        </div>
                      </div>
                      <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 text-xs font-bold shrink-0">
                        {h.distance_km} km
                      </Badge>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between text-xs text-muted-foreground border-t border-border pt-2">
                      <div className="flex items-center gap-3">
                        <span>Beds: <strong className="text-foreground">{h.beds}</strong></span>
                        {typeof h.rating === "number" && (
                          <span className="flex items-center gap-1 text-amber-600 font-semibold">
                            <Star className="size-3 fill-amber-400 text-amber-400" />
                            {h.rating.toFixed(1)}
                            <span className="text-muted-foreground font-normal">({h.review_count})</span>
                          </span>
                        )}
                      </div>
                      {h.contact_number && (
                        <span className="font-mono flex items-center gap-1">
                          <Phone className="size-3" /> {h.contact_number}
                        </span>
                      )}
                    </div>
                  </div>
                ))}

              {/* Donors List */}
              {includeDonors &&
                filteredDonors.map((d) => (
                  <div
                    key={d.id}
                    onClick={() => setFocusedMarkerId(d.id)}
                    className={`rounded-xl border p-4 bg-card cursor-pointer transition-all hover:border-rose-500 hover:shadow-sm ${
                      focusedMarkerId === d.id ? "border-rose-600 ring-2 ring-rose-500/20" : "border-border"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="flex size-7 items-center justify-center rounded-lg bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-400">
                          <Droplet className="size-4" />
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="font-bold text-sm leading-tight text-foreground">Donor #{d.donor_id}</h4>
                            <span className="text-xs font-extrabold text-rose-600 px-1.5 py-0.5 rounded bg-rose-50 border border-rose-200">
                              {d.blood_group}
                            </span>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {d.age ? `${d.age} yrs` : "Age not set"} · Last donation:{" "}
                            {d.last_donation_date ? new Date(d.last_donation_date).toLocaleDateString() : "Never"}
                          </p>
                        </div>
                      </div>
                      <Badge variant="outline" className="bg-rose-50 text-rose-700 border-rose-200 text-xs font-bold shrink-0">
                        {d.distance_km} km
                      </Badge>
                    </div>

                    <div className="mt-3 flex items-center justify-between text-xs border-t border-border pt-2">
                      <span className="flex items-center gap-1 text-emerald-600 font-medium">
                        {d.is_eligible ? (
                          <>
                            <CheckCircle2 className="size-3" /> Medically eligible
                          </>
                        ) : (
                          <>
                            <XCircle className="size-3 text-amber-600" />
                            <span className="text-amber-600">In cooldown</span>
                          </>
                        )}
                      </span>

                      <Button
                        size="sm"
                        variant="secondary"
                        className="h-7 text-xs gap-1 font-semibold"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleOpenContactModal(d.donor_id, d.blood_group);
                        }}
                      >
                        <Lock className="size-3" />
                        Request Contact
                      </Button>
                    </div>
                  </div>
                ))}

              {/* Blood Banks List */}
              {includeBloodBanks &&
                filteredBloodBanks.map((b) => (
                  <div
                    key={`bb-${b.id}`}
                    onClick={() => setFocusedMarkerId(`bank-${b.id}`)}
                    className={`rounded-xl border p-4 bg-card cursor-pointer transition-all hover:border-emerald-500 hover:shadow-sm ${
                      focusedMarkerId === `bank-${b.id}` ? "border-emerald-600 ring-2 ring-emerald-500/20" : "border-border"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="flex size-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
                          <Building2 className="size-4" />
                        </span>
                        <div>
                          <h4 className="font-bold text-sm leading-tight text-foreground">{b.name}</h4>
                          <p className="text-xs text-muted-foreground">{b.city}, {b.state}</p>
                        </div>
                      </div>
                      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs font-bold shrink-0">
                        {b.distance_km} km
                      </Badge>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center justify-between text-xs text-muted-foreground border-t border-border pt-2">
                      <span>Capacity: <strong className="text-foreground">{b.capacity} units</strong></span>
                      {b.contact_number && (
                        <span className="font-mono flex items-center gap-1">
                          <Phone className="size-3" /> {b.contact_number}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Donor Contact Consent Modal */}
      {selectedDonorForContact && (
        <DonorContactModal
          open={contactModalOpen}
          onOpenChange={setContactModalOpen}
          donorId={selectedDonorForContact.id}
          bloodGroup={selectedDonorForContact.bloodGroup}
        />
      )}
    </DashboardLayout>
  );
}
