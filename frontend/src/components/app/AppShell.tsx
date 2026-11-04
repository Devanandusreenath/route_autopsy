import { Link } from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { ModeIndicator } from "./status";

const nav = [
  { to: "/", label: "Route Investigation" },
  { to: "/autopsy", label: "Autopsy Lab" },
  { to: "/evidence", label: "Evidence Lab" },
  { to: "/vehicles", label: "Vehicle Profiles" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <Link to="/" className="font-mono text-sm font-bold tracking-widest">
            ROUTE<span className="text-primary">/</span>AUTOPSY
          </Link>
          <nav className="flex flex-wrap gap-1">
            {nav.map((n) => (
              <Link
                key={n.to}
                to={n.to}
                activeOptions={{ exact: true }}
                className="rounded px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground data-[status=active]:bg-secondary data-[status=active]:text-primary"
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <ModeIndicator />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
      <Toaster theme="dark" position="bottom-right" />
    </div>
  );
}
