import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  CheckCircle2,
  FileCode2,
  Mail,
  Plus,
  Radio,
  Send,
  Server,
  Shield,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "@/components/common/PageHeader";
import { SectionCard } from "@/components/common/SectionCard";
import { StatCard } from "@/components/common/StatCard";
import { StatusBadge } from "@/components/common/StatusBadge";
import { CardsSkeleton, EmptyState, TableSkeleton } from "@/components/common/StateBlocks";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useAsync } from "@/hooks/useAsync";
import { emailService, type ManagedRecipient } from "@/services/emails/emailService";

export const Route = createFileRoute("/app/emails")({
  head: () => ({
    meta: [
      { title: "Email Management — Blood Management System" },
      {
        name: "description",
        content:
          "Manage SMTP dispatch status, distribution lists, email templates and send controlled test emails.",
      },
      { property: "og:title", content: "Email Management — Blood Management System" },
      { property: "og:description", content: "Platform email services and recipient management." },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: EmailManagementPage,
});

function EmailManagementPage() {
  const status = useAsync(() => emailService.getEmailStatus());
  const recipients = useAsync(() => emailService.listRecipients());
  const templates = emailService.listTemplates();

  // Test Email State
  const [testEmail, setTestEmail] = useState("");
  const [testSubject, setTestSubject] = useState("[Test] Blood Management System Email Verification");
  const [testBody, setTestBody] = useState(
    "This is a test email verifying that the Blood Management System SMTP email service is operational.",
  );
  const [sendingTest, setSendingTest] = useState(false);

  // Add Recipient Modal State
  const [addOpen, setAddOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<ManagedRecipient["recipient_type"]>("EMERGENCY_DESK");
  const [addingRecipient, setAddingRecipient] = useState(false);

  const handleSendTest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testEmail.trim()) {
      toast.error("Please enter a valid destination email address.");
      return;
    }
    setSendingTest(true);
    try {
      const res = await emailService.sendTestEmail({
        recipient_email: testEmail.trim(),
        subject: testSubject.trim(),
        message: testBody.trim(),
      });
      toast.success(res.detail || `Test email dispatched to ${testEmail}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to dispatch test email. Check SMTP configuration.");
    } finally {
      setSendingTest(false);
    }
  };

  const handleAddRecipient = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEmail.trim() || !newName.trim()) {
      toast.error("Please provide both a recipient name and a valid email.");
      return;
    }
    setAddingRecipient(true);
    try {
      await emailService.createRecipient({
        email: newEmail.trim(),
        name: newName.trim(),
        recipient_type: newType,
        is_active: true,
      });
      toast.success("Recipient added to distribution list.");
      setAddOpen(false);
      setNewEmail("");
      setNewName("");
      setNewType("EMERGENCY_DESK");
      recipients.reload();
    } catch (err: any) {
      toast.error(err.message || "Failed to add email recipient.");
    } finally {
      setAddingRecipient(false);
    }
  };

  const handleDeleteRecipient = async (id: number, email: string) => {
    try {
      await emailService.deleteRecipient(id);
      toast.success(`Removed ${email} from distribution list.`);
      recipients.reload();
    } catch (err: any) {
      toast.error(err.message || "Failed to remove recipient.");
    }
  };

  return (
    <DashboardLayout title="Email Management">
      <PageHeader
        title="Email management"
        description="SMTP infrastructure health, distribution lists, notification templates, and delivery testing."
      />

      {status.loading || !status.data ? (
        <CardsSkeleton count={4} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="SMTP Service"
            value={status.data.smtp_configured ? "Operational" : "Console Mode"}
            icon={Server}
            tone={status.data.smtp_configured ? "success" : "warning"}
            hint={`Backend: ${status.data.email_backend}`}
          />
          <StatCard
            label="Default Sender"
            value="Default From"
            icon={Mail}
            hint={status.data.default_from_email}
          />
          <StatCard
            label="SMTP Host / Port"
            value={`${status.data.email_host}:${status.data.email_port}`}
            icon={Radio}
            tone="info"
            hint={status.data.use_tls ? "STARTTLS Encryption: Active" : "Unencrypted"}
          />
          <StatCard
            label="Managed Recipients"
            value={recipients.data?.length ?? 0}
            icon={Users}
            tone="primary"
            hint="System distribution contacts"
          />
        </div>
      )}

      <Tabs defaultValue="recipients" className="space-y-6">
        <TabsList>
          <TabsTrigger value="recipients">
            <Users className="mr-2 size-4" /> Recipient Distribution
          </TabsTrigger>
          <TabsTrigger value="test">
            <Send className="mr-2 size-4" /> Send Test Email
          </TabsTrigger>
          <TabsTrigger value="templates">
            <FileCode2 className="mr-2 size-4" /> Email Templates
          </TabsTrigger>
          <TabsTrigger value="status">
            <Shield className="mr-2 size-4" /> SMTP Security
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Managed Distribution Recipients */}
        <TabsContent value="recipients" className="space-y-4">
          <SectionCard
            title="Distribution recipients"
            description="External stakeholders and emergency services included in critical broadcast dispatches."
            bodyClassName="p-0"
            actions={
              <Dialog open={addOpen} onOpenChange={setAddOpen}>
                <DialogTrigger asChild>
                  <Button size="sm">
                    <Plus className="mr-2 size-4" /> Add Recipient
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <form onSubmit={handleAddRecipient}>
                    <DialogHeader>
                      <DialogTitle>Add distribution recipient</DialogTitle>
                      <DialogDescription>
                        Register an authorized recipient for emergency broadcasts and system notifications.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <Label htmlFor="recip-name">Full Name / Facility</Label>
                        <Input
                          id="recip-name"
                          placeholder="e.g. Metro Emergency Services"
                          value={newName}
                          onChange={(e) => setNewName(e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="recip-email">Email Address</Label>
                        <Input
                          id="recip-email"
                          type="email"
                          placeholder="e.g. emergency@cityhealth.gov"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="recip-type">Recipient Category</Label>
                        <Select
                          value={newType}
                          onValueChange={(val) => setNewType(val as ManagedRecipient["recipient_type"])}
                        >
                          <SelectTrigger id="recip-type">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="EMERGENCY_DESK">External Emergency Partner</SelectItem>
                            <SelectItem value="HOSPITAL">Hospital Contact</SelectItem>
                            <SelectItem value="BLOOD_BANK">Blood Bank Coordinator</SelectItem>
                            <SelectItem value="STAFF">Staff Member</SelectItem>
                            <SelectItem value="ADMIN">Administrator</SelectItem>
                            <SelectItem value="GENERAL">General Subscriber</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </div>
                    <DialogFooter>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => setAddOpen(false)}
                      >
                        Cancel
                      </Button>
                      <Button type="submit" disabled={addingRecipient}>
                        {addingRecipient ? "Adding..." : "Add Recipient"}
                      </Button>
                    </DialogFooter>
                  </form>
                </DialogContent>
              </Dialog>
            }
          >
            {recipients.loading ? (
              <TableSkeleton cols={5} />
            ) : !recipients.data || recipients.data.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={Users}
                  title="No managed recipients registered"
                  description="Add external emergency coordinators or staff to receive automated broadcasts."
                />
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Recipient</TableHead>
                    <TableHead>Email</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Added On</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recipients.data.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell className="font-medium">{r.name}</TableCell>
                      <TableCell>{r.email}</TableCell>
                      <TableCell>{r.recipient_type_display || r.recipient_type}</TableCell>
                      <TableCell>
                        <StatusBadge status={r.is_active ? "ACTIVE" : "SUSPENDED"} />
                      </TableCell>
                      <TableCell>
                        {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDeleteRecipient(r.id, r.email)}
                          aria-label={`Delete ${r.email}`}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </SectionCard>
        </TabsContent>

        {/* Tab 2: Test Outbound Email */}
        <TabsContent value="test" className="space-y-4">
          <SectionCard
            title="Controlled email dispatch test"
            description="Send a single test email through the configured SMTP server to verify network and deliverability."
          >
            <form onSubmit={handleSendTest} className="max-w-2xl space-y-4">
              <div className="space-y-2">
                <Label htmlFor="test-dest">Destination Email Address</Label>
                <Input
                  id="test-dest"
                  type="email"
                  placeholder="e.g. admin@example.com"
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="test-subj">Subject Line</Label>
                <Input
                  id="test-subj"
                  value={testSubject}
                  onChange={(e) => setTestSubject(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="test-body">Message Body</Label>
                <Textarea
                  id="test-body"
                  rows={4}
                  value={testBody}
                  onChange={(e) => setTestBody(e.target.value)}
                  required
                />
              </div>

              <Button type="submit" disabled={sendingTest}>
                <Send className="mr-2 size-4" />
                {sendingTest ? "Sending test message..." : "Dispatch Test Email"}
              </Button>
            </form>
          </SectionCard>
        </TabsContent>

        {/* Tab 3: System Email Templates */}
        <TabsContent value="templates" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {templates.map((tpl) => (
              <SectionCard
                key={tpl.id}
                title={tpl.name}
                description={tpl.category}
                actions={<StatusBadge status="ACTIVE" />}
              >
                <div className="space-y-3 text-sm">
                  <div>
                    <span className="font-semibold text-muted-foreground">Subject: </span>
                    <span className="font-mono text-xs font-medium text-foreground">
                      {tpl.subject}
                    </span>
                  </div>
                  <p className="text-muted-foreground">{tpl.description}</p>
                  <div className="rounded-md border bg-muted/40 p-2.5 text-xs">
                    <span className="font-medium text-primary">Trigger Event: </span>
                    <span className="text-muted-foreground">{tpl.triggers}</span>
                  </div>
                </div>
              </SectionCard>
            ))}
          </div>
        </TabsContent>

        {/* Tab 4: SMTP Security */}
        <TabsContent value="status" className="space-y-4">
          <SectionCard
            title="SMTP Security & Credentials Architecture"
            description="Platform email security guidelines."
          >
            <div className="space-y-4 text-sm">
              <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-4">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" />
                <div>
                  <h4 className="font-semibold">Credential Protection</h4>
                  <p className="text-muted-foreground">
                    SMTP authentication passwords and secret keys are stored exclusively in
                    server-side environment variables and are never transmitted to frontend clients.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-4">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" />
                <div>
                  <h4 className="font-semibold">Transport Layer Security (TLS)</h4>
                  <p className="text-muted-foreground">
                    All outbound SMTP dispatches use STARTTLS over port 587 to ensure encrypted
                    in-transit delivery to mail relays.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-lg border bg-muted/30 p-4">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" />
                <div>
                  <h4 className="font-semibold">Authoritative Recipient Filtering</h4>
                  <p className="text-muted-foreground">
                    Emergency broadcasts and automated alerts strictly validate recipient eligibility
                    and distance radius on the server before sending messages.
                  </p>
                </div>
              </div>
            </div>
          </SectionCard>
        </TabsContent>
      </Tabs>
    </DashboardLayout>
  );
}
