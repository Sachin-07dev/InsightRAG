import assert from "node:assert/strict";
import test from "node:test";
import { getApiOrigin } from "../src/lib/api-links.ts";

function withOrigin(value, assertion) {
  const original = process.env.NEXT_PUBLIC_API_BASE_URL;
  try {
    if (value === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = value;
    assertion();
  } finally {
    if (original === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
    else process.env.NEXT_PUBLIC_API_BASE_URL = original;
  }
}

test("unset public configuration uses the local browser API origin", () => {
  withOrigin(undefined, () =>
    assert.equal(getApiOrigin(), "http://localhost:8000"),
  );
});

test("an HTTP(S) origin is normalized without changing its port", () => {
  withOrigin("https://api.example.test:8443/", () => {
    assert.equal(getApiOrigin(), "https://api.example.test:8443");
  });
});

test("unsafe schemes, credential-bearing URLs and non-origin configuration are rejected", () => {
  for (const invalid of [
    "javascript:alert(1)",
    "ftp://api.example.test",
    "https://user:secret@api.example.test",
    "https://api.example.test/docs",
    "https://api.example.test?secret=value",
    "https://api.example.test#fragment",
    "not a URL",
    "",
  ]) {
    withOrigin(invalid, () => assert.throws(() => getApiOrigin()));
  }
});
