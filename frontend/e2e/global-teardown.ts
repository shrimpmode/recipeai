import { deleteTestData } from "./support/stack";

// The E2E stack shares the dev database; leave it as we found it. Seeded recipes carry
// placeholder embeddings that would otherwise surface in real AI searches.
export default function globalTeardown(): void {
  deleteTestData();
}
