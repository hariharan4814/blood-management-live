import { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { Info, Loader2, LocateFixed, MapPin } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LeafletMap } from "@/components/map/LeafletMap";
import { BLOOD_GROUPS } from "@/lib/types";
import { authService } from "@/services/auth/authService";

export const Route = createFileRoute("/register")({
  head: () => ({
    meta: [
      { title: "Register — Blood Management System" },
      {
        name: "description",
        content:
          "Create a donor or hospital account to donate blood, manage hospital facility requests and track inventory.",
      },
      { property: "og:title", content: "Register — Blood Management System" },
      { property: "og:description", content: "Donor and Hospital registration." },
    ],
  }),
  component: RegisterPage,
});

type PublicRole = "DONOR" | "HOSPITAL_STAFF";

const DEFAULT_COORDS: [number, number] = [13.0827, 80.2707]; // Chennai default

function RegisterPage() {
  const navigate = useNavigate();
  const [role, setRole] = useState<PublicRole>("DONOR");
  const [submitting, setSubmitting] = useState(false);
  const [geolocating, setGeolocating] = useState(false);

  type Errors = Partial<Record<"name" | "email" | "password" | "confirm" | "hospital" | "city" | "general", string>>;
  const [errors, setErrors] = useState<Errors>({});

  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    password: "",
    confirm: "",
    group: "O+",
    city: "Chennai",
    state: "Tamil Nadu",
    address: "",
    hospital: "",
    latitude: DEFAULT_COORDS[0] as number | null,
    longitude: DEFAULT_COORDS[1] as number | null,
  });

  const [, setHasCustomLocation] = useState<boolean>(false);

  const set = (key: keyof typeof form) => (value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      toast.error("Browser geolocation is not supported on this device.");
      return;
    }

    setGeolocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setForm((prev) => ({
          ...prev,
          latitude: Number(pos.coords.latitude.toFixed(6)),
          longitude: Number(pos.coords.longitude.toFixed(6)),
        }));
        setHasCustomLocation(true);
        setGeolocating(false);
        toast.success("Location coordinates set from your GPS.");
      },
      () => {
        setGeolocating(false);
        toast.error("Location permission denied. Click on the map to set your location pin.");
      },
      { enableHighAccuracy: true, timeout: 8000 }
    );
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Errors = {};
    if (!form.name.trim()) {
      next.name = role === "HOSPITAL_STAFF" ? "Contact person name is required." : "Full name is required.";
    }
    if (!/^\S+@\S+\.\S+$/.test(form.email)) next.email = "Enter a valid email address.";
    if (form.password.length < 8) next.password = "Use at least 8 characters.";
    if (form.password !== form.confirm) next.confirm = "Passwords do not match.";
    if (role === "HOSPITAL_STAFF" && !form.hospital.trim()) {
      next.hospital = "Hospital facility name is required.";
    }
    if (!form.city.trim()) next.city = "City is required.";

    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSubmitting(true);
    try {
      await authService.register({
        name: form.name.trim(),
        contact_person_name: form.name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        password: form.password,
        password_confirm: form.confirm,
        role,
        blood_group: form.group,
        city: form.city.trim(),
        state: form.state.trim(),
        address: form.address.trim(),
        hospital_name: form.hospital.trim(),
        hospital: form.hospital.trim(),
        latitude: form.latitude,
        longitude: form.longitude,
      });

      toast.success(
        role === "DONOR"
          ? "Donor account created successfully! You can sign in now."
          : "Hospital registered successfully! You can sign in now.",
      );
      navigate({ to: "/login" });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Registration failed. Please check your details.";
      setErrors({ general: msg });
    } finally {
      setSubmitting(false);
    }
  };

  const mapPosition: [number, number] = [
    typeof form.latitude === "number" ? form.latitude : DEFAULT_COORDS[0],
    typeof form.longitude === "number" ? form.longitude : DEFAULT_COORDS[1],
  ];

  return (
    <AuthLayout
      title="Create an account"
      description="Donors and hospitals can self-register. Admin, blood bank and lab accounts are created by administrators."
    >
      <Tabs value={role} onValueChange={(v) => setRole(v as PublicRole)}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="DONOR">Donor</TabsTrigger>
          <TabsTrigger value="HOSPITAL_STAFF">Hospital</TabsTrigger>
        </TabsList>
      </Tabs>

      <form onSubmit={onSubmit} className="mt-6 space-y-5">
        {errors.general ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
            {errors.general}
          </p>
        ) : null}

        {role === "HOSPITAL_STAFF" && (
          <Field label="Hospital Facility Name *" id="hospital" error={errors.hospital}>
            <Input
              id="hospital"
              value={form.hospital}
              onChange={(e) => set("hospital")(e.target.value)}
              placeholder="e.g. Apollo Speciality Hospital"
              disabled={submitting}
              required
            />
          </Field>
        )}

        <Field
          label={role === "HOSPITAL_STAFF" ? "Hospital / Staff Contact Person Name *" : "Full Name *"}
          id="name"
          error={errors.name}
        >
          <Input
            id="name"
            value={form.name}
            onChange={(e) => set("name")(e.target.value)}
            placeholder={role === "HOSPITAL_STAFF" ? "e.g. Dr. Rajesh Kumar" : "e.g. John Doe"}
            disabled={submitting}
            required
          />
        </Field>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Email Address *" id="email" error={errors.email}>
            <Input
              id="email"
              type="email"
              value={form.email}
              onChange={(e) => set("email")(e.target.value)}
              placeholder="contact@hospital.health"
              disabled={submitting}
              required
            />
          </Field>
          <Field label="Phone / Emergency Desk" id="phone">
            <Input
              id="phone"
              value={form.phone}
              onChange={(e) => set("phone")(e.target.value)}
              placeholder="+91-9876543210"
              disabled={submitting}
            />
          </Field>
        </div>

        {role === "DONOR" && (
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Blood group" id="group">
              <Select value={form.group} onValueChange={(v) => set("group")(v)} disabled={submitting}>
                <SelectTrigger id="group">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BLOOD_GROUPS.map((g) => (
                    <SelectItem key={g} value={g}>
                      {g}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="City *" id="city" error={errors.city}>
              <Input
                id="city"
                value={form.city}
                onChange={(e) => set("city")(e.target.value)}
                placeholder="e.g. Chennai"
                disabled={submitting}
                required
              />
            </Field>
          </div>
        )}

        {role === "HOSPITAL_STAFF" && (
          <>
            <div className="grid gap-5 sm:grid-cols-2">
              <Field label="City *" id="city" error={errors.city}>
                <Input
                  id="city"
                  value={form.city}
                  onChange={(e) => set("city")(e.target.value)}
                  placeholder="e.g. Chennai"
                  disabled={submitting}
                  required
                />
              </Field>
              <Field label="State / Province" id="state">
                <Input
                  id="state"
                  value={form.state}
                  onChange={(e) => set("state")(e.target.value)}
                  placeholder="e.g. Tamil Nadu"
                  disabled={submitting}
                />
              </Field>
            </div>

            <Field label="Physical Street Address" id="address">
              <Input
                id="address"
                value={form.address}
                onChange={(e) => set("address")(e.target.value)}
                placeholder="e.g. 21 Greams Lane, Thousand Lights"
                disabled={submitting}
              />
            </Field>
          </>
        )}

        {/* Location Picker Section */}
        <div className="space-y-2 rounded-xl border border-border bg-card/60 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-semibold">
              <MapPin className="size-4 text-primary" />
              <span>{role === "HOSPITAL_STAFF" ? "Hospital Map Location" : "Your Location Coordinates"}</span>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleUseCurrentLocation}
              disabled={geolocating || submitting}
              className="text-xs h-7 gap-1"
            >
              {geolocating ? <Loader2 className="size-3 animate-spin" /> : <LocateFixed className="size-3 text-primary" />}
              Use GPS
            </Button>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Tap or drag the pin on the map to set the exact facility location.
          </p>

          <LeafletMap
            center={mapPosition}
            selectedPosition={mapPosition}
            onPositionChange={(pos) => {
              setForm((prev) => ({
                ...prev,
                latitude: Number(pos[0].toFixed(6)),
                longitude: Number(pos[1].toFixed(6)),
              }));
              setHasCustomLocation(true);
            }}
            isPicker={true}
            height="h-[180px]"
          />

          <div className="grid grid-cols-2 gap-2 text-xs font-mono text-muted-foreground pt-1">
            <span>Lat: {form.latitude?.toFixed(6) ?? "Not set"}</span>
            <span className="text-right">Lng: {form.longitude?.toFixed(6) ?? "Not set"}</span>
          </div>
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Password *" id="password" error={errors.password}>
            <Input
              id="password"
              type="password"
              value={form.password}
              onChange={(e) => set("password")(e.target.value)}
              disabled={submitting}
              required
            />
          </Field>
          <Field label="Confirm Password *" id="confirm" error={errors.confirm}>
            <Input
              id="confirm"
              type="password"
              value={form.confirm}
              onChange={(e) => set("confirm")(e.target.value)}
              disabled={submitting}
              required
            />
          </Field>
        </div>

        <p className="flex gap-2 rounded-md border border-border bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          Super Admin, Blood Bank Admin and Lab Technician accounts cannot be self-registered — they are
          provisioned by an administrator.
        </p>

        <Button type="submit" size="lg" className="w-full" disabled={submitting}>
          {submitting ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
          {role === "DONOR" ? "Create donor account" : "Register hospital"}
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          Already registered?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}

function Field({
  label,
  id,
  error,
  children,
}: {
  label: string;
  id: string;
  error?: string | undefined;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
