import { Alert, Button, Code, Group, Modal, PasswordInput, Select, Stack, Text, Textarea } from "@mantine/core";
import { useEffect, useState } from "react";
import { useAuth } from "../lib/auth";
import { ErrorBox } from "./ui";

export type SignSubmit = (meaning: string, password: string, comment: string) => Promise<unknown>;

/**
 * Electronic signature dialog. Signing is a deliberate act: the signer re-enters their password, chooses the
 * meaning explicitly, and sees exactly which record and content hash they are signing.
 */
export function SignDialog(props: {
  opened: boolean; onClose: () => void; title: string; recordLabel: string; contentHash?: string | null;
  meanings: string[]; commentRequired?: string[]; onSubmit: SignSubmit;
}) {
  const { me } = useAuth();
  const [meaning, setMeaning] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (props.opened) {
      setMeaning(props.meanings.length === 1 ? props.meanings[0] : null);
      setPassword(""); setComment(""); setError(null);
    }
  }, [props.opened, props.meanings]);

  const needsComment = !!meaning && (props.commentRequired ?? []).includes(meaning);
  const submit = async () => {
    if (!meaning) return;
    setBusy(true); setError(null);
    try {
      await props.onSubmit(meaning, password, comment);
      props.onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal opened={props.opened} onClose={props.onClose} title={props.title} size="lg">
      <Stack>
        <div className="kv">
          <dt>Record</dt><dd><span className="ident">{props.recordLabel}</span></dd>
          {props.contentHash && (<><dt>Content hash</dt><dd><Code>{props.contentHash}</Code></dd></>)}
          <dt>Signer</dt><dd>{me?.full_name} ({me?.username})</dd>
        </div>
        <Select label="Meaning of signature" data={props.meanings} value={meaning} onChange={setMeaning}
          placeholder="Choose what you are signing for" required allowDeselect={false} />
        <Textarea label={needsComment ? "Comment (required)" : "Comment"} value={comment}
          onChange={(e) => setComment(e.currentTarget.value)} autosize minRows={2} required={needsComment} />
        <PasswordInput label="Re-enter your password to sign" value={password} autoComplete="current-password"
          onChange={(e) => setPassword(e.currentTarget.value)} required />
        <Alert variant="light" color="gray">
          <Text size="sm">
            Your signature will be recorded with your name, the date and time, and the meaning selected, and is
            permanently linked to this record. It cannot be edited or removed.
          </Text>
        </Alert>
        <ErrorBox error={error} />
        <Group justify="flex-end">
          <Button variant="default" onClick={props.onClose}>Cancel</Button>
          <Button onClick={submit} loading={busy}
            disabled={!meaning || !password || (needsComment && !comment.trim())}>
            Sign {meaning ? `“${meaning}”` : ""}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
