import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { JsonSourceEditor } from "./JsonSourceEditor";
import { OptionOrder } from "./OptionOrder";
import { PredictionDisclosure } from "./PredictionDisclosure";
import { ExpectedAnswers } from "./ExpectedAnswers";
it("preserves incomplete source text without JSON parsing or numeric conversion", () => {
  const onChange = vi.fn();
  const source = '{"large":9007199254740993,"x":0.1234567890123456789,';
  render(<JsonSourceEditor label="Input JSON" value="" onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Input JSON"), {
    target: { value: source },
  });
  expect(onChange).toHaveBeenCalledWith(source);
});
it("moves options by keyboard with stable IDs", async () => {
  function Example() {
    const [options, setOptions] = useState([
      { id: "a", name: "First" },
      { id: "b", name: "Second" },
    ]);
    return (
      <OptionOrder
        options={options}
        onChange={(value) => setOptions([...value])}
      />
    );
  }
  render(<Example />);
  const user = userEvent.setup();
  const move = screen.getByRole("button", { name: "Move Second up" });
  move.focus();
  await user.keyboard("{Enter}");
  expect(screen.getAllByRole("listitem")[0].textContent).toContain("Second");
  expect(screen.getByRole("status").textContent).toBe(
    "Second moved to position 1.",
  );
});
it("unmounts hidden predictions and resets disclosure on case changes", async () => {
  const user = userEvent.setup();
  const { rerender } = render(
    <PredictionDisclosure
      caseIdentity="case-a"
      source="run-1"
      prediction="Private A"
    />,
  );
  expect(screen.queryByText("Private A")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Reveal prediction" }));
  expect(screen.getByText("Private A")).toBeTruthy();
  rerender(
    <PredictionDisclosure
      caseIdentity="case-b"
      source="run-1"
      prediction="Private B"
    />,
  );
  expect(screen.queryByText("Private A")).toBeNull();
  expect(screen.queryByText("Private B")).toBeNull();
});
it("stages expected answers without saving or treating empty selection as clear", async () => {
  const save = vi.fn();
  const change = vi.fn();
  const user = userEvent.setup();
  render(
    <ExpectedAnswers
      options={[{ id: "a", name: "A" }]}
      selected={[]}
      onChange={change}
      onSave={save}
    />,
  );
  await user.click(screen.getByRole("checkbox", { name: "A" }));
  expect(change).toHaveBeenCalledWith(["a"]);
  expect(save).not.toHaveBeenCalled();
  expect(
    (
      screen.getByRole("button", {
        name: "Save expected answer",
      }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);
});

it("keeps staged content when Save fails and returns focus to editing", async () => {
  const { StagedDialog } = await import("./Modal");
  const { ApiError } = await import("../api/client");
  const close = vi.fn();
  const user = userEvent.setup();
  render(
    <StagedDialog
      title="Expected answer"
      dirty
      onSave={async () => {
        throw new ApiError(
          "conflict",
          "The input changed. Review it before saving.",
        );
      }}
      onDiscard={vi.fn()}
      onClose={close}
    >
      <JsonSourceEditor
        label="Input source"
        value={'{"integer":9007199254740993,'}
      />
    </StagedDialog>,
  );
  await user.click(
    screen.getByRole("button", { name: "Close Expected answer" }),
  );
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  expect(
    await screen.findByText("The input changed. Review it before saving."),
  ).toBeTruthy();
  expect(close).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Keep editing" }));
  expect(
    (screen.getByLabelText("Input source") as HTMLTextAreaElement).value,
  ).toBe('{"integer":9007199254740993,');
  expect(document.activeElement).toBe(screen.getByLabelText("Input source"));
});
