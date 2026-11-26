using System;
using System.Globalization;
using GtaAnything.Runtime.Compatibility;

namespace GtaAnything.Runtime.Streaming
{
    /// <summary>
    /// Outcome of a Gate 3 (Model Stream) + Gate 4 (World Vehicle Spawn) operation.
    /// </summary>
    public sealed class StreamSpawnResult
    {
        private readonly bool _success;
        private readonly bool _usedFallback;
        private readonly string _resolvedModelName;
        private readonly IVehicleHandle _vehicle;
        private readonly string _errorMessage;

        public bool Success { get { return _success; } }
        public bool UsedFallback { get { return _usedFallback; } }
        public string ResolvedModelName { get { return _resolvedModelName; } }
        public IVehicleHandle Vehicle { get { return _vehicle; } }
        public string ErrorMessage { get { return _errorMessage; } }

        public StreamSpawnResult(
            bool success,
            bool usedFallback,
            string resolvedModelName,
            IVehicleHandle vehicle,
            string errorMessage = null)
        {
            _success = success;
            _usedFallback = usedFallback;
            _resolvedModelName = resolvedModelName;
            _vehicle = vehicle;
            _errorMessage = errorMessage;
        }
    }

    /// <summary>
    /// Enforces Gate 3 &amp; Gate 4 asset safety:
    /// 1. Requests preferred addon model with bounded timeout.
    /// 2. MANDATORILY calls <see cref="IGtaWorldHost.ReleaseModelRequest"/> (MarkAsNoLongerNeeded)
    ///    if streaming times out so no dangling streaming handle leaks in Gen9.
    /// 3. Falls back deterministically to <c>vanillaFallbackModel</c>.
    /// 4. Null-guards <see cref="IGtaWorldHost.SpawnVehicle"/> and checks <c>Exists()</c> before returning.
    /// </summary>
    public sealed class SafeModelStreamer
    {
        private const int DefaultPollStepMs = 50;
        private readonly IGtaWorldHost _host;

        public IGtaWorldHost Host { get { return _host; } }

        public SafeModelStreamer(IGtaWorldHost host)
        {
            if (host == null)
            {
                throw new ArgumentNullException("host");
            }
            _host = host;
        }

        /// <summary>
        /// Requests a model and polls until loaded or <paramref name="timeoutMs"/> elapses.
        /// On timeout, immediately releases the model request (<c>MarkAsNoLongerNeeded</c>).
        /// </summary>
        public bool RequestModelWithTimeout(
            string modelName,
            int timeoutMs = 5000,
            Func<int, bool> pollWait = null)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }

            string normalized = modelName.Trim();
            int effectiveTimeout = Math.Max(0, timeoutMs);

            _host.RequestModel(normalized);
            if (_host.HasModelLoaded(normalized))
            {
                return true;
            }

            int elapsed = 0;
            while (elapsed < effectiveTimeout)
            {
                int step = Math.Min(DefaultPollStepMs, effectiveTimeout - elapsed);
                if (pollWait != null)
                {
                    if (!pollWait(step))
                    {
                        break;
                    }
                }
                elapsed += step;

                if (_host.HasModelLoaded(normalized))
                {
                    return true;
                }
            }

            // Hard Invariant #5: Always release timed-out model requests to avoid dangling streaming handles.
            _host.ReleaseModelRequest(normalized);
            return false;
        }

        /// <summary>
        /// Streams the preferred addon model (or falls back to the required vanilla baseline model)
        /// and spawns the vehicle with strict non-null and <c>Exists()</c> validation.
        /// </summary>
        public StreamSpawnResult StreamAndSpawnVehicle(
            string preferredAddonModel,
            string vanillaFallbackModel,
            float x,
            float y,
            float z,
            float heading = 0f,
            int timeoutMs = 5000,
            Func<int, bool> pollWait = null)
        {
            if (string.IsNullOrWhiteSpace(vanillaFallbackModel))
            {
                throw new ArgumentException(
                    "Hard Invariant Violation: vanillaFallbackModel must never be null or empty.",
                    "vanillaFallbackModel");
            }

            string fallback = vanillaFallbackModel.Trim();
            string resolvedModel = fallback;
            bool usedFallback = false;

            if (!string.IsNullOrWhiteSpace(preferredAddonModel))
            {
                string preferred = preferredAddonModel.Trim();
                if (RequestModelWithTimeout(preferred, timeoutMs, pollWait))
                {
                    resolvedModel = preferred;
                }
                else
                {
                    usedFallback = true;
                    resolvedModel = fallback;
                }
            }

            // If we fell back or had no preferred addon, ensure the vanilla fallback model is streamed.
            if (string.Equals(resolvedModel, fallback, StringComparison.OrdinalIgnoreCase))
            {
                if (!RequestModelWithTimeout(fallback, timeoutMs, pollWait))
                {
                    return new StreamSpawnResult(
                        success: false,
                        usedFallback: usedFallback,
                        resolvedModelName: fallback,
                        vehicle: null,
                        errorMessage: string.Format(
                            CultureInfo.InvariantCulture,
                            "Both preferred model '{0}' and vanilla fallback '{1}' failed Gate 3 streaming.",
                            preferredAddonModel,
                            fallback));
                }
            }

            // Gate 4: Spawn vehicle and strictly verify non-null handle before touching any vehicle properties.
            IVehicleHandle vehicle = _host.SpawnVehicle(resolvedModel, x, y, z, heading);
            _host.ReleaseModelRequest(resolvedModel);

            if (vehicle == null || !vehicle.Exists())
            {
                return new StreamSpawnResult(
                    success: false,
                    usedFallback: usedFallback,
                    resolvedModelName: resolvedModel,
                    vehicle: null,
                    errorMessage: string.Format(
                        CultureInfo.InvariantCulture,
                        "Gate 4 Failure: SpawnVehicle returned null or non-existent handle for '{0}'.",
                        resolvedModel));
            }

            return new StreamSpawnResult(
                success: true,
                usedFallback: usedFallback,
                resolvedModelName: resolvedModel,
                vehicle: vehicle,
                errorMessage: null);
        }
    }
}
