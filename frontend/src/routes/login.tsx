import { useState } from "react";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { AuthLayout } from "@/components/layout/AuthLayout";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ROLE_LABELS } from "@/lib/types";
import { useAuth } from "@/providers/AuthProvider";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Login — Blood Management System" },
      {
        name: "description",
        content: "Sign in to the Blood Management System to manage donations, inventory and requests.",
      },
      { property: "og:title", content: "Login — Blood Management System" },
      { property: "og:description", content: "Role-based sign in for the Blood Management System." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { login, loading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const loginIdentifier = email.trim();
    if (!loginIdentifier || !password.trim()) {
      setError("Enter both email/username and password to continue.");
      return;
    }

    try {
      const user = await login({ email: loginIdentifier, password, remember });
      toast.success(`Signed in as ${ROLE_LABELS[user.role]}`);
      navigate({ to: "/app/dashboard" });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Invalid credentials. Please try again.";
      setError(msg);
    }
  };

  return (
    <AuthLayout title="Sign in" description="Access your role-based dashboard.">
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@hospital.health"
            disabled={loading}
            required
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
            required
          />
        </div>

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={remember} onCheckedChange={(v) => setRemember(Boolean(v))} />
            Remember me
          </label>
          <Link to="/forgot-password" className="text-sm font-medium text-primary hover:underline">
            Forgot password?
          </Link>
        </div>

        {error ? (
          <p className="rounded-md border border-destructive/30 bg-destructive/8 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button type="submit" className="w-full" size="lg" disabled={loading}>
          {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
          Sign in
        </Button>

        <p className="text-center text-sm text-muted-foreground">
          New donor or hospital?{" "}
          <Link to="/register" className="font-medium text-primary hover:underline">
            Create an account
          </Link>
        </p>
      </form>
    </AuthLayout>
  );
}
