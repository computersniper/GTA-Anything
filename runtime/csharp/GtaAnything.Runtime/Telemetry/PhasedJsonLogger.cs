using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;

namespace GtaAnything.Runtime.Telemetry
{
    /// <summary>
    /// Writes structured JSON Lines (.jsonl) telemetry mapped to the 7-Layer Acceptance Evidence Ladder (L1..L7).
    /// Consumed offline by <c>gta_anything.diagnose.log_correlator</c> to correlate script phases with
    /// ScriptHookV.log, ScriptHookVDotNet.log, and RagePluginHook.log.
    /// </summary>
    public sealed class PhasedJsonLogger : IDisposable
    {
        private readonly object _writeLock = new object();
        private readonly List<string> _inMemoryEntries = new List<string>();
        private bool _disposed;

        public string ModId { get; }
        public string LogFilePath { get; }
        public IReadOnlyList<string> Entries => _inMemoryEntries;

        public PhasedJsonLogger(string modId, string logFilePath = null)
        {
            ModId = string.IsNullOrWhiteSpace(modId) ? "unknown_mod" : modId.Trim();
            LogFilePath = string.IsNullOrWhiteSpace(logFilePath) ? null : logFilePath.Trim();

            if (!string.IsNullOrEmpty(LogFilePath))
            {
                string dir = Path.GetDirectoryName(LogFilePath);
                if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
                {
                    Directory.CreateDirectory(dir);
                }
            }
        }

        /// <summary>
        /// Records a structured event tied to an acceptance layer (e.g. "L1".."L7") and lifecycle phase.
        /// </summary>
        public void LogEvent(
            string layer,
            string phase,
            string eventName,
            string details = "",
            string error = null)
        {
            string normalizedLayer = NormalizeLayer(layer);
            string timestampUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture);

            StringBuilder sb = new StringBuilder(256);
            sb.Append('{');
            AppendJsonField(sb, "timestampUtc", timestampUtc, prependComma: false);
            AppendJsonField(sb, "modId", ModId, prependComma: true);
            AppendJsonField(sb, "layer", normalizedLayer, prependComma: true);
            AppendJsonField(sb, "phase", phase ?? "unknown", prependComma: true);
            AppendJsonField(sb, "event", eventName ?? "unspecified", prependComma: true);
            AppendJsonField(sb, "details", details ?? string.Empty, prependComma: true);
            if (error != null)
            {
                AppendJsonField(sb, "error", error, prependComma: true);
            }
            else
            {
                sb.Append(",\"error\":null");
            }
            sb.Append('}');

            string line = sb.ToString();
            lock (_writeLock)
            {
                _inMemoryEntries.Add(line);
                if (!string.IsNullOrEmpty(LogFilePath) && !_disposed)
                {
                    File.AppendAllText(LogFilePath, line + Environment.NewLine, Encoding.UTF8);
                }
            }
        }

        /// <summary>
        /// Convenience helper for logging a reached acceptance milestone (1 through 7).
        /// </summary>
        public void LogLayerReached(int layerNumber, string phase, string eventName, string details = "")
        {
            int clamped = Math.Max(1, Math.Min(7, layerNumber));
            LogEvent($"L{clamped}", phase, eventName, details, error: null);
        }

        /// <summary>
        /// Records an exception event with its type and message.
        /// </summary>
        public void LogException(string layer, string phase, Exception ex)
        {
            string err = ex == null ? "UnknownException" : $"{ex.GetType().Name}: {ex.Message}";
            LogEvent(layer, phase, "UnhandledException", details: ex?.StackTrace ?? string.Empty, error: err);
        }

        public void Dispose()
        {
            lock (_writeLock)
            {
                _disposed = true;
            }
        }

        private static string NormalizeLayer(string layer)
        {
            if (string.IsNullOrWhiteSpace(layer))
            {
                return "L3";
            }
            string trimmed = layer.Trim().ToUpperInvariant();
            if (trimmed.StartsWith("L", StringComparison.Ordinal) && trimmed.Length == 2 && char.IsDigit(trimmed[1]))
            {
                return trimmed;
            }
            if (trimmed.Length == 1 && char.IsDigit(trimmed[0]))
            {
                return "L" + trimmed;
            }
            return trimmed;
        }

        private static void AppendJsonField(StringBuilder sb, string key, string value, bool prependComma)
        {
            if (prependComma)
            {
                sb.Append(',');
            }
            sb.Append('"').Append(EscapeJson(key)).Append("\":\"").Append(EscapeJson(value)).Append('"');
        }

        private static string EscapeJson(string input)
        {
            if (string.IsNullOrEmpty(input))
            {
                return string.Empty;
            }

            StringBuilder escaped = new StringBuilder(input.Length + 8);
            foreach (char c in input)
            {
                switch (c)
                {
                    case '\\':
                        escaped.Append("\\\\");
                        break;
                    case '"':
                        escaped.Append("\\\"");
                        break;
                    case '\r':
                        escaped.Append("\\r");
                        break;
                    case '\n':
                        escaped.Append("\\n");
                        break;
                    case '\t':
                        escaped.Append("\\t");
                        break;
                    default:
                        if (c < 0x20)
                        {
                            escaped.AppendFormat(CultureInfo.InvariantCulture, "\\u{0:X4}", (int)c);
                        }
                        else
                        {
                            escaped.Append(c);
                        }
                        break;
                }
            }
            return escaped.ToString();
        }
    }
}
