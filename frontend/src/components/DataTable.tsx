import type { ReactNode } from "react";
export interface Column<T> {
  key: string;
  heading: string;
  render: (row: T) => ReactNode;
}
export function DataTable<T>({
  caption,
  rows,
  columns,
  rowId,
}: {
  caption: string;
  rows: readonly T[];
  columns: readonly Column<T>[];
  rowId: (row: T) => string;
}) {
  return (
    <div
      className="table-region"
      role="region"
      aria-label={caption}
      tabIndex={0}
    >
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col">
                {column.heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowId(row)}>
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
