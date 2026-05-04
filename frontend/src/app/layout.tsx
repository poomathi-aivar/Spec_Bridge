import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { ToastProvider } from "@/components/Toast";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "SPEC BRIDGE",
  description:
    "Transform business documents into actionable technical specifications using AI",
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/projects/new", label: "New Project" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={cn(
          geistSans.variable,
          geistMono.variable,
          "antialiased min-h-screen bg-background text-foreground"
        )}
      >
        <div className="flex min-h-screen">
          {/* Sidebar Navigation */}
          <aside className="hidden md:flex md:w-64 md:shrink-0 md:flex-col border-r border-border bg-card">
            <div className="flex h-16 items-center gap-2 border-b border-border px-6">
              <span
                className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground font-bold text-sm"
                aria-hidden="true"
              >
                SB
              </span>
              <span className="text-lg font-semibold tracking-tight text-foreground">
                SPEC BRIDGE
              </span>
            </div>
            <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Main navigation">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>

          {/* Main Content Area */}
          <div className="flex min-w-0 flex-1 flex-col">
            {/* Header */}
            <header className="flex h-16 shrink-0 items-center gap-4 border-b border-border bg-card px-6">
              {/* Mobile brand mark */}
              <div className="flex items-center gap-2 md:hidden">
                <span
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground font-bold text-sm"
                  aria-hidden="true"
                >
                  SB
                </span>
                <span className="text-lg font-semibold tracking-tight text-foreground">
                  SPEC BRIDGE
                </span>
              </div>
              {/* Mobile navigation */}
              <nav className="flex items-center gap-4 md:hidden ml-auto" aria-label="Mobile navigation">
                {navItems.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
              {/* Desktop: empty header space for future use (search, user menu, etc.) */}
              <div className="hidden md:block" />
            </header>

            {/* Page Content */}
            <main className="flex-1 overflow-x-hidden p-6">
              <ToastProvider>{children}</ToastProvider>
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
