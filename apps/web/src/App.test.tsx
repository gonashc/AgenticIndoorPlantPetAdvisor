import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

    fireEvent.click(screen.getByRole("radio", { name: /Cat/ }));

    expect(screen.getByLabelText("Affection style")).toBeTruthy();
    expect(screen.getByText("Protected by Google sign-in")).toBeTruthy();
  });

  it("updates the profile snapshot as preferences change", () => {
    render(<App />);

    const profile = within(screen.getByLabelText("Current match profile"));
    expect(profile.getByText("Plant match")).toBeTruthy();
    expect(profile.getByText("Beginner experience")).toBeTruthy();
    expect(profile.getByText("Bright indirect light")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Your experience"), { target: { value: "EXPERT" } });
    fireEvent.click(screen.getByRole("radio", { name: /Dog/ }));

    expect(profile.getByText("Dog match")).toBeTruthy();
    expect(profile.getByText("Expert experience")).toBeTruthy();
    expect(profile.getByText("Medium activity")).toBeTruthy();

    fireEvent.click(screen.getByRole("radio", { name: /Cat/ }));
    expect(profile.getByText("Cat match")).toBeTruthy();
  });
});
