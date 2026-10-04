# Pick Narrated Litter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Narrate" tool in the sidebar, directly above "Remove". The user clicks it, then clicks a piece of litter on the map, and that litter becomes the one Shelly's voice narrates on the next Play.

**Architecture:** Frontend only. The app already narrates `selectedParticleId` (`App.tsx` builds the story from `selectedTrajectory`). The new tool is a second, explicit way to set that id: `OceanMap` routes a click on a litter particle to the existing `onSelect` callback while the tool is active, and `App.selectParticle` switches the tool back to `explore` once a litter is picked. No backend change.

**Tech Stack:** React 19, TypeScript, Vitest, Testing Library, Mapbox GL.

**Spec:** No separate spec file. The design was agreed in chat and is summarised in this header.

## Global Constraints

- The Narrate button sits in the tool list directly above Remove (second to last entry of the `tools` array, before `remove`). "Reset all" stays last.
- The tool id is exactly `"narrate"`. Label `Narrate`, detail `Pick a litter`.
- Only litter (the `particles-layer`) can be picked. Cleanup collectors cannot.
- Picking a litter returns the tool to `explore`.
- Clicking litter in `explore` mode must keep working exactly as today (same message).
- No backend changes, no new files besides this plan. Keep the diff small.
- Frontend checks run from the repo root: `npx vitest run` (baseline: 17 passed across 3 files), `npm run lint`, `npm run build`.
- Work happens on branch `feature/pick-narrated-litter`. Never push.

---

### Task 1: Narrate tool

**Files:**
- Modify: `src/types.ts` (add `"narrate"` to `Tool`)
- Modify: `src/App.tsx` (tool entry, `placeItem` guard, `selectParticle`)
- Modify: `src/OceanMap.tsx` (click and cursor handling)
- Modify: `src/styles.css` (icon colour)
- Test: `src/App.test.tsx` (extend the `OceanMap` mock, add one test)

- [ ] **Step 1: Write the failing test**

In `src/App.test.tsx`, replace the `OceanMap` mock so it also exposes `onSelect`:

```tsx
vi.mock("./OceanMap", () => ({
  OceanMap: ({ onPlace, onSelect, frames, trajectories }: {
    onPlace: (coordinates: Coordinates) => void;
    onSelect: (id: string) => void;
    frames: unknown[];
    trajectories: Array<{ id: string }>;
  }) => <>
    <button onClick={() => onPlace([-130, 40])}>Drop at test ocean point</button>
    {trajectories.map(({ id }, index) => (
      <button key={id} onClick={() => onSelect(id)}>Pick litter {index + 1}</button>
    ))}
    <output data-testid="frames">{JSON.stringify(frames)}</output>
  </>,
}));
```

Append this block at the end of the file:

```tsx
describe("narrate tool", () => {
  it("narrates the litter picked with the Narrate tool", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: /Bottle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    fireEvent.click(screen.getByRole("button", { name: "Drop at test ocean point" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Pick litter 2" })).toBeTruthy());
    const firstId = vi.mocked(requestSimulation).mock.calls.at(-1)![0][0].id;

    const narrate = screen.getByRole("button", { name: /Narrate/ });
    fireEvent.click(narrate);
    expect(narrate.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Pick litter 1" }));

    expect(narrate.getAttribute("aria-pressed")).toBe("false");
    await waitFor(() => expect(screen.getByText("Shelly will tell this bottle's story. Press play to hear it!")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Play simulation and narration" }));
    await waitFor(() => expect(requestStoryForRun).toHaveBeenCalledWith("run-2", firstId));
  });
});
```

(The second bottle placed is the default selection, so asking for the first one's story proves the pick took effect.)

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/App.test.tsx`
Expected: the new test fails because no button named `Narrate` exists. The other tests still pass.

- [ ] **Step 3: Implement**

`src/types.ts`:

```ts
export type Tool = "explore" | PlacementType | "narrate" | "remove";
```

`src/App.tsx`: add `Mic` to the `lucide-react` import, and add the tool entry directly before `remove`:

```ts
  { id: "narrate", label: "Narrate", detail: "Pick a litter", icon: Mic },
```

`placeItem` guard (first line of the function):

```ts
    if (tool === "explore" || tool === "narrate" || tool === "remove") return;
```

`selectParticle`: after `setSelectedParticleId(id);` add:

```ts
    if (tool === "narrate") {
      setTool("explore");
      setMessage(`Shelly will tell this ${trajectory.type}'s story. Press play to hear it!`);
      return;
    }
```

`src/OceanMap.tsx`, in `handleClick`, let the narrate tool share the explore branch:

```ts
      if (activeTool === "explore" || activeTool === "narrate") {
```

and in `handleMouseMove`, add a branch between the `explore` and `remove` branches:

```ts
      } else if (activeTool === "narrate") {
        const hasLitter = Boolean(map.getLayer("particles-layer"))
          && map.queryRenderedFeatures(event.point, { layers: ["particles-layer"] }).length > 0;
        map.getCanvas().style.cursor = hasLitter ? "pointer" : "not-allowed";
```

`src/styles.css`, directly above `.tool-icon--remove`:

```css
.tool-icon--narrate { background: #ece4ff; color: #6b4fc4; }
```

- [ ] **Step 4: Verify**

Run from the repo root: `npx vitest run` (expect 18 passed), `npm run lint`, `npm run build`. All three must be clean.

- [ ] **Step 5: Commit**

```bash
git add src/types.ts src/App.tsx src/OceanMap.tsx src/styles.css src/App.test.tsx
git commit -m "feat(frontend): add a Narrate tool to pick which litter Shelly narrates"
```
