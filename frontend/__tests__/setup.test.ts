describe("Jest setup", () => {
  it("should run tests successfully", () => {
    expect(1 + 1).toBe(2);
  });

  it("should support TypeScript", () => {
    const greeting: string = "Hello, SPEC BRIDGE";
    expect(greeting).toContain("SPEC BRIDGE");
  });
});
