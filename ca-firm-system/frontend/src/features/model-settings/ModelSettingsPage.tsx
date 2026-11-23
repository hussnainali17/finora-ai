import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  MenuItem,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useCallback, useEffect, useState } from 'react';
import {
  clearTaskOverride,
  getAgents,
  listModels,
  setAgentConfig,
  setGlobalDefaultModel,
  setModelEnabled,
  setPolicy,
  setTaskOverride,
  testModel,
  usageSummary,
} from '../../services/llmApi';
import type { LlmAgent, LlmAgents, LlmModels, LlmUsageSummary } from '../../types/llm';
import { useAuth } from '../auth/AuthContext';

const NONE = '';
const label = (models: LlmModels | null, alias: string) =>
  models?.models.find((m) => m.alias === alias)?.display_name ?? alias;
const humanise = (s: string) => s.replace(/_/g, ' ');

export default function ModelSettingsPage() {
  const { can } = useAuth();
  const manage = can('llm:manage');
  const select = can('llm:select');
  const [models, setModels] = useState<LlmModels | null>(null);
  const [agents, setAgents] = useState<LlmAgents | null>(null);
  const [usage, setUsage] = useState<LlmUsageSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, a] = await Promise.all([listModels(), getAgents()]);
      setModels(m);
      setAgents(a);
      if (manage) setUsage(await usageSummary());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load model settings');
    }
  }, [manage]);
  useEffect(() => {
    void load();
  }, [load]);

  const act = async (fn: () => Promise<unknown>, done?: string) => {
    setError(null);
    setNotice(null);
    try {
      await fn();
      if (done) setNotice(done);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The change could not be saved');
    }
  };

  if (!models || !agents) {
    return error ? (
      <Alert severity="error">{error}</Alert>
    ) : (
      <CircularProgress aria-label="Loading model settings" />
    );
  }
  const anyEnabled = models.models.some((m) => m.enabled);

  return (
    <Stack spacing={4}>
      <Box>
        <Typography variant="h5" component="h2">
          AI model settings
        </Typography>
        <Typography color="text.secondary">
          Only models approved by the platform are listed. Nothing is sent to any provider until a
          model is enabled for your firm. Configuration version {models.config_version}.
        </Typography>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      {notice && <Alert severity="success">{notice}</Alert>}
      {!anyEnabled && (
        <Alert severity="info">
          No model is enabled, so AI assistance is off and documents are processed with
          deterministic rules only.
        </Alert>
      )}
      {!manage && (
        <Alert severity="info">
          You can view these settings; only a firm admin can change them.
        </Alert>
      )}

      <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label="Approved models">
          <TableHead>
            <TableRow>
              <TableCell>Model</TableCell>
              <TableCell>Provider</TableCell>
              <TableCell>Capabilities</TableCell>
              <TableCell>Gateway</TableCell>
              <TableCell>Enabled</TableCell>
              {manage && <TableCell>Connection</TableCell>}
            </TableRow>
          </TableHead>
          <TableBody>
            {models.models.map((m) => (
              <ModelRow
                key={m.alias}
                m={m}
                manage={manage}
                onToggle={(v) =>
                  act(
                    () => setModelEnabled(m.alias, v),
                    `${m.display_name} ${v ? 'enabled' : 'disabled'}`,
                  )
                }
                onTest={() => testModel(m.alias)}
              />
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2.5, backgroundColor: 'background.paper' }}>
        <Typography variant="h6" component="h3" gutterBottom>
          Global default model
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Choose a primary model that will be applied as the default across all agents (Intake, Accounting Review, Adjustments, Reporting, CA Review).
        </Typography>
        <GlobalDefaultSelector
          models={models}
          manage={manage}
          onApply={(alias, fallback) =>
            act(
              () => setGlobalDefaultModel(alias, fallback),
              `Global default model updated to ${label(models, alias)} across all agents`,
            )
          }
        />
      </Paper>

      <Box>
        <Typography variant="h6" component="h3" gutterBottom>
          Agent defaults
        </Typography>
        <Stack spacing={2}>
          {agents.agents.map((a) => (
            <AgentCard
              key={a.key}
              agent={a}
              models={models}
              manage={manage}
              select={select && agents.allow_task_overrides}
              onSave={(d, f) => act(() => setAgentConfig(a.key, d, f), `${a.label} settings saved`)}
              onOverride={(task, alias) =>
                act(
                  () =>
                    alias === NONE
                      ? clearTaskOverride(a.key, task)
                      : setTaskOverride(a.key, task, alias),
                  'Task model updated',
                )
              }
            />
          ))}
        </Stack>
      </Box>

      <Box>
        <Typography variant="h6" component="h3">
          Task-level selection
        </Typography>
        <FormControlLabel
          control={
            <Switch
              checked={agents.allow_task_overrides}
              disabled={!manage}
              onChange={(_, v) =>
                void act(
                  () => setPolicy(v),
                  v ? 'Task-level selection allowed' : 'Task-level selection turned off',
                )
              }
              slotProps={{ input: { 'aria-label': 'Allow task-level model selection' } }}
            />
          }
          label="Allow reviewers to pick a different approved model for a specific task"
        />
      </Box>

      {manage && (
        <Box>
          <Typography variant="h6" component="h3" gutterBottom>
            Usage
          </Typography>
          {usage.length === 0 ? (
            <Typography color="text.secondary">No AI calls have been made yet.</Typography>
          ) : (
            <Paper variant="outlined" sx={{ overflowX: 'auto' }}>
              <Table size="small" aria-label="Usage summary">
                <TableHead>
                  <TableRow>
                    <TableCell>Model</TableCell>
                    <TableCell>Agent</TableCell>
                    <TableCell align="right">Calls</TableCell>
                    <TableCell align="right">Errors</TableCell>
                    <TableCell align="right">Fallbacks</TableCell>
                    <TableCell align="right">Tokens</TableCell>
                    <TableCell align="right">Cost (USD)</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {usage.map((u) => (
                    <TableRow key={`${u.alias}/${u.agent}`}>
                      <TableCell>{label(models, u.alias)}</TableCell>
                      <TableCell>{humanise(u.agent)}</TableCell>
                      <TableCell align="right">{u.calls}</TableCell>
                      <TableCell align="right">{u.errors}</TableCell>
                      <TableCell align="right">{u.fallbacks}</TableCell>
                      <TableCell align="right">{u.tokens}</TableCell>
                      <TableCell align="right">
                        {u.cost_usd === null ? '-' : Number(u.cost_usd).toFixed(4)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </Box>
      )}
    </Stack>
  );
}

function ModelRow({
  m,
  manage,
  onToggle,
  onTest,
}: {
  m: LlmModels['models'][number];
  manage: boolean;
  onToggle: (v: boolean) => void;
  onTest: () => Promise<{ ok: boolean }>;
}) {
  const [result, setResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult((await onTest()).ok ? 'Working' : 'Failed');
    } catch {
      setResult('Failed');
    } finally {
      setBusy(false);
    }
  };
  const inUse = m.used_by.length > 0;
  return (
    <TableRow>
      <TableCell>
        <Typography fontWeight={600}>{m.display_name}</Typography>
        <Typography variant="caption" color="text.secondary">
          {m.description}
        </Typography>
      </TableCell>
      <TableCell>{m.provider}</TableCell>
      <TableCell>
        <Stack direction="row" gap={0.5} flexWrap="wrap">
          {m.capabilities.map((c) => (
            <Chip key={c} size="small" label={humanise(c)} />
          ))}
          <Chip
            size="small"
            variant="outlined"
            label={`${Math.round(m.context_window / 1000)}k context`}
          />
        </Stack>
      </TableCell>
      <TableCell>
        {m.available === null ? 'Unknown' : m.available ? 'Available' : 'Not configured'}
      </TableCell>
      <TableCell>
        <Switch
          checked={m.enabled}
          disabled={!manage || (m.enabled && inUse)}
          onChange={(_, v) => onToggle(v)}
          slotProps={{ input: { 'aria-label': `Enable ${m.display_name}` } }}
        />
        {m.enabled && inUse && (
          <Typography variant="caption" display="block">
            In use by {m.used_by.map(humanise).join(', ')}
          </Typography>
        )}
      </TableCell>
      {manage && (
        <TableCell>
          <Button size="small" onClick={() => void run()} disabled={busy}>
            Test {m.display_name}
          </Button>
          {result && <Typography variant="caption">{result}</Typography>}
        </TableCell>
      )}
    </TableRow>
  );
}

function GlobalDefaultSelector({
  models,
  manage,
  onApply,
}: {
  models: LlmModels;
  manage: boolean;
  onApply: (alias: string, fallback: string | null) => void;
}) {
  const enabledModels = models.models.filter((m) => m.enabled);
  const [selectedDefault, setSelectedDefault] = useState(
    enabledModels.find((m) => m.alias === 'hy4-flash')?.alias ?? enabledModels[0]?.alias ?? NONE,
  );
  const [selectedFallback, setSelectedFallback] = useState(NONE);

  const fallbackOpts = enabledModels.filter((m) => m.alias !== selectedDefault);

  return (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
      <TextField
        select
        size="small"
        sx={{ minWidth: 260 }}
        label="Select Global Default Model"
        value={selectedDefault}
        disabled={!manage || enabledModels.length === 0}
        onChange={(e) => {
          setSelectedDefault(e.target.value);
          if (selectedFallback === e.target.value) {
            setSelectedFallback(NONE);
          }
        }}
        helperText={enabledModels.length === 0 ? 'Enable at least one model in the table above' : ''}
      >
        {enabledModels.length === 0 ? (
          <MenuItem value={NONE}>No models enabled</MenuItem>
        ) : (
          enabledModels.map((m) => (
            <MenuItem key={m.alias} value={m.alias}>
              {m.display_name} ({m.provider})
            </MenuItem>
          ))
        )}
      </TextField>

      <TextField
        select
        size="small"
        sx={{ minWidth: 240 }}
        label="Global Fallback Model (Optional)"
        value={selectedFallback}
        disabled={!manage || selectedDefault === NONE || fallbackOpts.length === 0}
        onChange={(e) => setSelectedFallback(e.target.value)}
      >
        <MenuItem value={NONE}>None</MenuItem>
        {fallbackOpts.map((m) => (
          <MenuItem key={m.alias} value={m.alias}>
            {m.display_name} ({m.provider})
          </MenuItem>
        ))}
      </TextField>

      {manage && (
        <Button
          variant="contained"
          disabled={selectedDefault === NONE}
          onClick={() => onApply(selectedDefault, selectedFallback === NONE ? null : selectedFallback)}
          sx={{ height: 40 }}
        >
          Set as Default for All Agents
        </Button>
      )}
    </Stack>
  );
}

function AgentCard({
  agent,
  models,
  manage,
  select,
  onSave,
  onOverride,
}: {
  agent: LlmAgent;
  models: LlmModels;
  manage: boolean;
  select: boolean;
  onSave: (d: string, f: string | null) => void;
  onOverride: (task: string, alias: string) => void;
}) {
  const [def, setDef] = useState(agent.default_alias ?? NONE);
  const [fb, setFb] = useState(agent.fallback_alias ?? NONE);
  useEffect(() => {
    setDef(agent.default_alias ?? NONE);
    setFb(agent.fallback_alias ?? NONE);
  }, [agent.default_alias, agent.fallback_alias]);
  const dirty = def !== (agent.default_alias ?? NONE) || fb !== (agent.fallback_alias ?? NONE);
  const opts = (exclude?: string) =>
    agent.eligible
      .filter((a) => a !== exclude)
      .map((a) => (
        <MenuItem key={a} value={a}>
          {label(models, a)}
        </MenuItem>
      ));
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography fontWeight={600}>{agent.label}</Typography>
      {agent.tasks.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          This agent has no AI-assisted tasks yet.
        </Typography>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} mt={1} alignItems="flex-start">
        <TextField
          select
          size="small"
          sx={{ minWidth: 220 }}
          label={`${agent.label} default model`}
          value={def}
          disabled={!manage}
          onChange={(e) => setDef(e.target.value)}
        >
          <MenuItem value={NONE}>Not set (AI off)</MenuItem>
          {opts()}
        </TextField>
        <TextField
          select
          size="small"
          sx={{ minWidth: 220 }}
          label={`${agent.label} fallback model`}
          value={fb}
          disabled={!manage || def === NONE}
          onChange={(e) => setFb(e.target.value)}
        >
          <MenuItem value={NONE}>No fallback</MenuItem>
          {opts(def)}
        </TextField>
        {manage && (
          <Button
            variant="contained"
            disabled={!dirty || def === NONE}
            onClick={() => onSave(def, fb === NONE ? null : fb)}
            aria-label={`Save ${agent.label}`}
          >
            Save
          </Button>
        )}
      </Stack>
      {agent.tasks.map((t) => (
        <Box key={t.task} mt={2}>
          <Typography variant="body2">
            <strong>{humanise(t.task)}</strong> - {t.description}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Using {t.effective_alias ? label(models, t.effective_alias) : 'no model (AI off)'}
            {t.source === 'task_override' ? ' (task override)' : ''}
          </Typography>
          {select && (
            <TextField
              select
              size="small"
              sx={{ mt: 1, display: 'block', maxWidth: 260 }}
              label={`Model for ${humanise(t.task)}`}
              value={t.override_alias ?? NONE}
              onChange={(e) => onOverride(t.task, e.target.value)}
            >
              <MenuItem value={NONE}>Use agent default</MenuItem>
              {t.eligible.map((a) => (
                <MenuItem key={a} value={a}>
                  {label(models, a)}
                </MenuItem>
              ))}
            </TextField>
          )}
        </Box>
      ))}
    </Paper>
  );
}
