import assert from "node:assert/strict";
import test from "node:test";
import { toFiniteNumbers } from "../src/lib/visualization.ts";

test("verified decimal strings become chart numbers without changing row order", () => {
  assert.deepEqual(
    toFiniteNumbers([
      { label: "Jan", value: "100.1000", source_rows: 1 },
      { label: "Feb", value: "-4.2500", source_rows: 1 },
      { label: "Mar", value: null, source_rows: 0 },
    ]),
    [100.1, -4.25, null],
  );
});

test("malformed and non-finite values fail before chart rendering", () => {
  for (const value of ["NaN", "Infinity", "1,000", "1e9999"]) {
    assert.throws(() =>
      toFiniteNumbers([{ label: "x", value, source_rows: 1 }]),
    );
  }
});
