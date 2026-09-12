import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { App } from "./App";

afterEach(cleanup);

describe("App", () => {
  it("shows only the questions required by the selected category", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Find the right life for your home." })).toBeTruthy();
    expect(screen.getByLabelText("Light")).toBeTruthy();
    expect(screen.queryByLabelText("Affection style")).toBeNull();

    fireEvent.click(screen.getByRole("radio", { name: /Dog/ }));

    expect(screen.queryByLabelText("Light")).toBeNull();
    expect(screen.queryByLabelText("Affection style")).toBeNull();
    expect(screen.getByLabelText("Outdoor space")).toBeTruthy();
    expect(screen.getByText("Protected by Google sign-in")).toBeTruthy();
  });
});
