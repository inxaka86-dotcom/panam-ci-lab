import { describe, it, expect } from 'vitest';
import { Editor } from '@tiptap/core';
import Document from '@tiptap/extension-document';
import Paragraph from '@tiptap/extension-paragraph';
import Text from '@tiptap/extension-text';
import { TextSelection } from '@tiptap/pm/state';
import { TrackChanges, Insertion, Deletion, revisions } from '../src/lib/editor/extensions/trackChanges';
import { buildDocx } from '../src/lib/export/docx';
import { importDocx } from '../src/lib/import/docx';

const AI_AUTHOR = 'PANAM AI TEST';
const MARGINS = { top: 2, bottom: 2, left: 2, right: 2 };

function reviewEditor(text: string) {
  const el = document.createElement('div');
  document.body.appendChild(el);
  return new Editor({
    element: el,
    extensions: [
      Document,
      Paragraph,
      Text,
      Insertion,
      Deletion,
      TrackChanges.configure({ recording: () => true, author: () => AI_AUTHOR }),
    ],
    content: `<p>${text}</p>`,
  });
}

async function replace(editor: Editor, needle: string, replacement: string) {
  const plain = editor.state.doc.textContent;
  const index = plain.indexOf(needle);
  expect(index).toBeGreaterThanOrEqual(0);
  const from = index + 1;
  const to = from + needle.length;
  editor.view.dispatch(
    editor.state.tr
      .setSelection(TextSelection.create(editor.state.doc, from, to))
      .replaceSelectionWith(editor.state.schema.text(replacement), false),
  );
  await Promise.resolve();
}

function marksOf(node: any, type: string, out: any[] = []): any[] {
  for (const mark of node?.marks ?? []) if (mark.type === type) out.push(mark);
  for (const child of node?.content ?? []) marksOf(child, type, out);
  return out;
}

describe('public legal-review compatibility canary', () => {
  it('records a synthetic AI replacement as deletion + insertion and requires human decision', async () => {
    const editor = reviewEditor('Исполнитель уведомляет Заказчика за один день.');
    await replace(editor, 'один день', 'пять рабочих дней');

    const list = revisions(editor.state.doc);
    expect(list.map((r) => [r.kind, r.text])).toEqual([
      ['deletion', 'один день'],
      ['insertion', 'пять рабочих дней'],
    ]);
    expect(list.every((r) => r.author === AI_AUTHOR)).toBe(true);

    // No automatic decision: both revisions remain until an explicit command is called.
    expect(revisions(editor.state.doc)).toHaveLength(2);
    editor.commands.rejectRevisions(true);
    expect(editor.state.doc.textContent).toBe('Исполнитель уведомляет Заказчика за один день.');
    editor.destroy();
  });

  it('keeps only the replacement after explicit acceptance', async () => {
    const editor = reviewEditor('Срок уведомления — один день.');
    await replace(editor, 'один день', 'пять рабочих дней');
    editor.commands.acceptRevisions(true);
    expect(editor.state.doc.textContent).toBe('Срок уведомления — пять рабочих дней.');
    expect(revisions(editor.state.doc)).toHaveLength(0);
    editor.destroy();
  });

  it('round-trips a synthetic AI comment thread and resolved state through DOCX', async () => {
    const comment = {
      id: 'panam-test-comment-1',
      author: AI_AUTHOR,
      date: '2026-09-30T00:00:00.000Z',
      text: 'Проверить баланс условия об одностороннем отказе.',
      replies: [{
        author: 'Юрист TEST',
        date: '2026-09-30T00:01:00.000Z',
        text: 'Принято к проверке.',
      }],
      resolved: true,
    };
    const doc: any = {
      type: 'doc',
      content: [{
        type: 'paragraph',
        content: [
          { type: 'text', text: 'Условие: ' },
          { type: 'text', text: 'односторонний отказ', marks: [{ type: 'comment', attrs: comment }] },
          { type: 'text', text: '.' },
        ],
      }],
    };

    const bytes = await buildDocx(doc, MARGINS, 'portrait');
    const back: any = importDocx(bytes).content;
    const comments = marksOf(back, 'comment');

    expect(comments).toHaveLength(1);
    expect(comments[0].attrs.author).toBe(AI_AUTHOR);
    expect(comments[0].attrs.text).toBe(comment.text);
    expect(comments[0].attrs.resolved).toBe(true);
    expect(comments[0].attrs.replies).toEqual(comment.replies);
  });
});
