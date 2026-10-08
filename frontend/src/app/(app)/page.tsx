import { SearchPanel } from "@/components/search/search-panel";

export default function SearchPage() {
  return (
    <>
      <header className="mb-8">
        <h1 className="font-serif text-4xl font-medium tracking-tight sm:text-5xl">What would you like to eat?</h1>
        <p className="mt-3 max-w-xl text-muted">
          Describe a craving and let AI pick recipes that suit your goals, or search names and ingredients directly.
        </p>
      </header>
      <SearchPanel />
    </>
  );
}
