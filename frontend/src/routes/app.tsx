import { Navigate, Outlet, createFileRoute, useLocation } from "@tanstack/react-router";
import { Loader } from "@/components/common/Loader";
import { useAuth } from "@/providers/AuthProvider";
import type { Role } from "@/lib/types";

export const Route = createFileRoute("/app")({
  component: AppLayoutRoute,
});

/**
 * Role-based permission map for application routes.
 */
const ROUTE_PERMISSIONS: Record<string, Role[]> = {
  "/app/users": ["SUPER_ADMIN"],
  "/app/emails": ["SUPER_ADMIN"],
  "/app/blood-banks": ["SUPER_ADMIN"],
  "/app/hospitals": ["SUPER_ADMIN"],
  "/app/settings": ["SUPER_ADMIN"],
  "/app/audit-logs": ["SUPER_ADMIN"],
  "/app/inventory": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN"],
  "/app/donors": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN"],
  "/app/sos": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN"],
  "/app/requests": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN", "HOSPITAL_STAFF", "DONOR"],
  "/app/request-history": ["SUPER_ADMIN", "HOSPITAL_STAFF"],
  "/app/tests": ["SUPER_ADMIN", "LAB_TECHNICIAN", "BLOOD_BANK_ADMIN"],
  "/app/test-history": ["SUPER_ADMIN", "LAB_TECHNICIAN", "BLOOD_BANK_ADMIN"],
  "/app/camps": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN", "DONOR"],
  "/app/donation-history": ["SUPER_ADMIN", "DONOR"],
  "/app/notifications": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN", "HOSPITAL_STAFF", "LAB_TECHNICIAN", "DONOR"],
  "/app/profile": ["DONOR", "SUPER_ADMIN", "BLOOD_BANK_ADMIN", "HOSPITAL_STAFF", "LAB_TECHNICIAN"],
  "/app/map": ["DONOR", "SUPER_ADMIN", "BLOOD_BANK_ADMIN", "HOSPITAL_STAFF", "LAB_TECHNICIAN"],
  "/app/analytics": ["SUPER_ADMIN", "BLOOD_BANK_ADMIN"],
};

/**
 * Authentication and role-aware route protection guard.
 */
function AppLayoutRoute() {
  const { user, hydrated, isAuthenticated } = useAuth();
  const location = useLocation();

  // Show loading indicator while session/token initialization is underway
  if (!hydrated) {
    return (
      <div className="grid min-h-screen place-items-center bg-background">
        <Loader label="Preparing your workspace" size={56} />
      </div>
    );
  }

  // Redirect to login if user is not authenticated
  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />;
  }

  // Check role-based access for the current route
  const currentPath = location.pathname.replace(/\/$/, "");
  const allowedRoles = ROUTE_PERMISSIONS[currentPath];

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/app/dashboard" replace />;
  }

  return <Outlet />;
}
