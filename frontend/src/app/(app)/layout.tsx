import { Nav } from "@/components/nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="mx-auto w-full max-w-3xl px-4 pb-24 pt-10 sm:px-6">{children}</main>
    </>
  );
}
