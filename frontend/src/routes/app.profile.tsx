import { useEffect, useState, useRef } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { Camera, CheckCircle2, Loader2, Trash2, User, XCircle } from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { TableSkeleton } from "@/components/common/StateBlocks";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
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
import { BLOOD_GROUPS, ROLE_LABELS, type BloodGroup } from "@/lib/types";
import { useAuth } from "@/providers/AuthProvider";
import { ProfileLocationPicker } from "@/components/map/ProfileLocationPicker";
import {
  profileService,
  type DonorDetails,
  type DonorEligibility,
  type UserProfile,
} from "@/services/profile/profileService";

export const Route = createFileRoute("/app/profile")({
  head: () => ({
    meta: [
      { title: "My Profile — Blood Management System" },
      {
        name: "description",
        content: "Maintain your profile details, contact information and eligibility status.",
      },
      { property: "og:title", content: "My Profile — Blood Management System" },
      { property: "og:description", content: "Maintain your profile details and eligibility information." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: ProfilePage,
});

function ProfilePage() {
  const { user: authUser, refreshUser } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [donor, setDonor] = useState<DonorDetails | null>(null);
  const [eligibility, setEligibility] = useState<DonorEligibility | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingImage, setUploadingImage] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [form, setForm] = useState({
    firstName: "",
    lastName: "",
    email: "",
    phone: "",
    bloodGroup: "" as BloodGroup | "",
    dob: "",
    weightKg: "",
  });

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await profileService.getProfile();
      setProfile(p);
      const initialBloodGroup = p.blood_group || "";
      setForm((prev) => ({
        ...prev,
        firstName: p.first_name || "",
        lastName: p.last_name || "",
        email: p.email || "",
        phone: p.phone || "",
        bloodGroup: initialBloodGroup || prev.bloodGroup || (p.role === "DONOR" ? "O+" : ""),
      }));

      if (p.role === "DONOR") {
        const [d, elig] = await Promise.all([
          profileService.getDonorDetails(),
          profileService.getDonorEligibility(),
        ]);
        if (d) {
          setDonor(d);
          setForm((prev) => ({
            ...prev,
            bloodGroup: d.blood_group || prev.bloodGroup || "O+",
            dob: d.date_of_birth || "",
            weightKg: d.weight_kg ? String(d.weight_kg) : "",
          }));
        } else {
          setForm((prev) => ({
            ...prev,
            bloodGroup: prev.bloodGroup || "O+",
          }));
        }
        if (elig) {
          setEligibility(elig);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load profile.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);

    try {
      if (profile?.role === "DONOR" && (!form.bloodGroup || !form.dob || !form.weightKg)) {
        throw new Error("Enter your blood group, date of birth, and weight to complete your donor profile.");
      }
      const selectedBloodGroup = form.bloodGroup || undefined;
      const updated = await profileService.updateProfile({
        first_name: form.firstName.trim(),
        last_name: form.lastName.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        blood_group: (selectedBloodGroup as BloodGroup) || undefined,
      });

      setProfile(updated);

      if (profile?.role === "DONOR") {
        const updatedDonor = await profileService.updateDonorDetails({
          blood_group: selectedBloodGroup as BloodGroup,
          date_of_birth: form.dob,
          weight_kg: parseFloat(form.weightKg),
        });
        setDonor(updatedDonor);

        const updatedElig = await profileService.getDonorEligibility();
        if (updatedElig) setEligibility(updatedElig);
      }

      await refreshUser();
      toast.success("Profile updated successfully.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to update profile.";
      setError(msg);
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 2 * 1024 * 1024) {
      toast.error("Profile picture must be smaller than 2 MB.");
      return;
    }

    setUploadingImage(true);
    try {
      const updated = await profileService.uploadProfileImage(file);
      setProfile(updated);
      await refreshUser();
      toast.success("Profile picture updated.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to upload image.");
    } finally {
      setUploadingImage(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteImage = async () => {
    setUploadingImage(true);
    try {
      await profileService.deleteProfileImage();
      if (profile) {
        setProfile({ ...profile, profile_image: null, profile_image_url: null });
      }
      await refreshUser();
      toast.success("Profile picture removed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to delete image.");
    } finally {
      setUploadingImage(false);
    }
  };

  const handleSaveLocation = async (loc: { latitude: number; longitude: number; address: string }) => {
    try {
      const updated = await profileService.updateProfile({
        latitude: loc.latitude,
        longitude: loc.longitude,
        address: loc.address,
      });
      setProfile(updated);
      if (profile?.role === "DONOR" && donor) {
        setDonor({ ...donor, latitude: loc.latitude, longitude: loc.longitude });
      }
      await refreshUser();
      toast.success("Location saved successfully.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to save location.");
    }
  };

  return (
    <DashboardLayout title="My Profile">
      <PageHeader
        title={profile?.role === "DONOR" ? "Donor profile" : "User profile"}
        description="Maintain your personal information, contact credentials, and profile picture."
      />

      {loading ? (
        <SectionCard>
          <TableSkeleton rows={6} cols={2} />
        </SectionCard>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-6">
            {/* Avatar Section */}
            <SectionCard title="Profile Picture" description="JPEG, PNG or WEBP (Max 2MB)">
              <div className="flex flex-wrap items-center gap-6">
                <Avatar className="size-20 border-2 border-border shadow-sm">
                  {profile?.profile_image_url ? (
                    <AvatarImage src={profile.profile_image_url} alt={profile.full_name} />
                  ) : null}
                  <AvatarFallback className="bg-primary/10 text-primary text-xl font-bold">
                    {profile?.first_name?.charAt(0) || profile?.username?.charAt(0) || <User className="size-8" />}
                  </AvatarFallback>
                </Avatar>

                <div className="flex flex-wrap items-center gap-3">
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleImageUpload}
                    accept="image/jpeg,image/png,image/webp"
                    className="hidden"
                    id="profile-image-input"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={uploadingImage}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploadingImage ? (
                      <Loader2 className="mr-2 size-4 animate-spin" />
                    ) : (
                      <Camera className="mr-2 size-4" />
                    )}
                    {profile?.profile_image_url ? "Change photo" : "Upload photo"}
                  </Button>

                  {profile?.profile_image_url ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:bg-destructive/10"
                      disabled={uploadingImage}
                      onClick={handleDeleteImage}
                    >
                      <Trash2 className="mr-2 size-4" />
                      Remove
                    </Button>
                  ) : null}
                </div>
              </div>
            </SectionCard>

            {/* Personal Details Form */}
            <SectionCard title="Personal details" description="Update your contact credentials and identification">
              <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSave}>
                {error ? (
                  <p className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive sm:col-span-2">
                    {error}
                  </p>
                ) : null}

                <div className="grid gap-2">
                  <Label htmlFor="firstName">First name</Label>
                  <Input
                    id="firstName"
                    value={form.firstName}
                    onChange={(e) => setForm({ ...form, firstName: e.target.value })}
                    disabled={saving}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="lastName">Last name</Label>
                  <Input
                    id="lastName"
                    value={form.lastName}
                    onChange={(e) => setForm({ ...form, lastName: e.target.value })}
                    disabled={saving}
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                    disabled={saving}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="phone">Phone</Label>
                  <Input
                    id="phone"
                    value={form.phone}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    disabled={saving}
                    placeholder="+1 555-0199"
                  />
                </div>

                <div className="grid gap-2">
                  <Label htmlFor="username">Username (read-only)</Label>
                  <Input id="username" value={profile?.username || ""} disabled className="bg-muted text-muted-foreground" />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="role">Role (read-only)</Label>
                  <div className="flex h-10 items-center">
                    <StatusBadge status={profile?.role || "DONOR"} />
                  </div>
                </div>

                {profile?.role === "DONOR" ? (
                  <>
                    <div className="grid gap-2">
                      <Label htmlFor="bloodGroup">Blood group *</Label>
                      <Select
                        value={form.bloodGroup}
                        onValueChange={(val) => setForm({ ...form, bloodGroup: val as BloodGroup })}
                        disabled={saving}
                      >
                        <SelectTrigger id="bloodGroup">
                          <SelectValue placeholder="Select blood group" />
                        </SelectTrigger>
                        <SelectContent>
                          {BLOOD_GROUPS.map((bg) => (
                            <SelectItem key={bg} value={bg}>
                              {bg}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="dob">Date of birth</Label>
                      <Input
                        id="dob"
                        type="date"
                        value={form.dob}
                        onChange={(e) => setForm({ ...form, dob: e.target.value })}
                        disabled={saving}
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="weight">Weight (kg)</Label>
                      <Input
                        id="weight"
                        type="number"
                        step="0.1"
                        min="30"
                        max="250"
                        value={form.weightKg}
                        onChange={(e) => setForm({ ...form, weightKg: e.target.value })}
                        disabled={saving}
                      />
                    </div>
                  </>
                ) : null}

                <div className="sm:col-span-2 pt-2">
                  <Button type="submit" disabled={saving}>
                    {saving ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                    Save changes
                  </Button>
                </div>
              </form>
            </SectionCard>

            {/* Location & Proximity Section */}
            <SectionCard
              title="Location & Proximity"
              description="Drop a pin on OpenStreetMap or use browser GPS to find nearby blood resources."
            >
              <ProfileLocationPicker
                initialLatitude={profile?.latitude}
                initialLongitude={profile?.longitude}
                initialAddress={profile?.address}
                onSave={handleSaveLocation}
              />
            </SectionCard>
          </div>

          {/* Donor Summary & Eligibility Panel */}
          {profile?.role === "DONOR" && donor ? (
            <div className="space-y-6">
              <SectionCard title="Donation Summary">
                <dl className="space-y-4 text-sm">
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Donor ID</dt>
                    <dd className="font-mono text-xs">DONOR-{donor.id}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Blood group</dt>
                    <dd className="text-xl font-extrabold text-primary">{donor.blood_group}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Age</dt>
                    <dd className="font-semibold">{donor.age ? `${donor.age} yrs` : "Not set"}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Weight</dt>
                    <dd className="font-semibold">{donor.weight_kg ? `${donor.weight_kg} kg` : "Not set"}</dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Last donation</dt>
                    <dd>
                      {donor.last_donation_date
                        ? new Date(donor.last_donation_date).toLocaleDateString()
                        : "Never donated"}
                    </dd>
                  </div>
                  <div className="flex items-center justify-between">
                    <dt className="text-muted-foreground">Eligibility status</dt>
                    <dd>
                      <span
                        className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                          eligibility?.is_eligible
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                            : "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border border-amber-200 dark:border-amber-800"
                        }`}
                      >
                        {eligibility?.is_eligible ? (
                          <>
                            <CheckCircle2 className="size-3.5" /> Eligible
                          </>
                        ) : (
                          <>
                            <XCircle className="size-3.5" /> Ineligible
                          </>
                        )}
                      </span>
                    </dd>
                  </div>
                </dl>

                {eligibility && !eligibility.is_eligible && eligibility.reasons.length > 0 ? (
                  <div className="mt-4 rounded-md border border-amber-200 bg-amber-50/50 p-3 text-xs text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
                    <p className="font-medium mb-1">Eligibility requirements:</p>
                    <ul className="list-disc pl-4 space-y-0.5">
                      {eligibility.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </SectionCard>
            </div>
          ) : (
            <SectionCard title="Account Details">
              <dl className="space-y-4 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Account role</dt>
                  <dd className="font-semibold">{profile ? ROLE_LABELS[profile.role] : ""}</dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Verification status</dt>
                  <dd>
                    <StatusBadge status={profile?.is_verified ? "ACTIVE" : "PENDING"} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Member since</dt>
                  <dd>{profile?.date_joined ? new Date(profile.date_joined).toLocaleDateString() : ""}</dd>
                </div>
              </dl>
            </SectionCard>
          )}
        </div>
      )}
    </DashboardLayout>
  );
}
