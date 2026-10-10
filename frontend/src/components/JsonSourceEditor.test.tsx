import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { useState } from "react";
import { JsonSourceEditor } from "./JsonSourceEditor";

const exactSource = '{"large":9007199254740993,"value":"ab"}';

it("keeps exact source and the insertion caret through controlled edits", async () => {
  function Harness() {
    const [source, setSource] = useState(exactSource);
    return <JsonSourceEditor label="Exact source" value={source} onChange={setSource} />;
  }

  const user = userEvent.setup();
  render(<Harness />);
  const editor = screen.getByLabelText("Exact source") as HTMLTextAreaElement;
  const insertionPoint = exactSource.indexOf("ab") + 1;
  editor.focus();
  editor.setSelectionRange(insertionPoint, insertionPoint);
  await user.keyboard("X");

  expect(editor.value).toBe('{"large":9007199254740993,"value":"aXb"}');
  expect(editor.selectionStart).toBe(insertionPoint + 1);
});

it("forwards composition boundaries while retaining the exact composing string", () => {
  const boundaries: string[] = [];
  function Harness() {
    const [source, setSource] = useState(exactSource);
    return (
      <JsonSourceEditor
        label="Composed source"
        value={source}
        onChange={setSource}
        onCompositionStart={() => boundaries.push("start")}
        onCompositionEnd={() => boundaries.push("end")}
      />
    );
  }
  render(<Harness />);
  const editor = screen.getByLabelText("Composed source") as HTMLTextAreaElement;
  fireEvent.compositionStart(editor);
  fireEvent.change(editor, { target: { value: `${exactSource}字` } });
  expect(editor.value).toBe(`${exactSource}字`);
  fireEvent.compositionEnd(editor);
  expect(boundaries).toEqual(["start", "end"]);
});
