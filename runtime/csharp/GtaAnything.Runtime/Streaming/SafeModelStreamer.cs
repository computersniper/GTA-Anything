using System;
using GtaAnything.Runtime.Compatibility;

namespace GtaAnything.Runtime.Streaming
{
    /// <summary>
    /// Outcome of a Gate 3 (Model Stream) + Gate 4 (World Vehicle Spawn) operation.
    /// </summary>
    public sealed class StreamSpawnResult
    {
        public bool Success { get; }
        public bool UsedFallback { get; }
        public string ResolvedModelName { get; }
        public IVehicleHandle Vehicle { get; }
        public string ErrorMessage { get; }

        public StreamSpawnResult(
            bool success,
            bool usedFallback,
            string resolvedModelName,
            IVehicleHandle vehicle,
            string errorMessage = null)
        {
            Success = success;
            UsedFallback = usedFallback;
            ResolvedModelName = resolvedModelName;
            Vehicle = vehicle;
            ErrorMessage = errorMessage;
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

        public IGtaWorldHost Host { get; }

        public SafeModelStreamer(IGtaWorldHost host)
        {
            Host = host ?? throw new ArgumentNullException(nameof(host));
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

            Host.RequestModel(normalized);
            if (Host.HasModelLoaded(normalized))
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

                if (Host.HasModelLoaded(normalized))
                {
                    return true;
                }
            }

            // Hard Invariant #5: Always release timed-out model requests to avoid dangling streaming handles.
            Host.ReleaseModelRequest(normalized);
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
            int timeoutMs = 5000)
        {
            if (string.IsNullOrWhiteSpace(vanillaFallbackModel))
            {
                throw new ArgumentException(
                    "Hard Invariant Violation: vanillaFallbackModel must never be null or empty.",
                    nameof(vanillaFallbackModel));
            }

            string fallback = vanillaFallbackModel.Trim();
            string resolvedModel = fallback;
            bool usedFallback = false;

            if (!string.IsNullOrWhiteSpace(preferredAddonModel))
            {
                string preferred = preferredAddonModel.Trim();
                if (RequestModelWithTimeout(preferred, timeoutMs))
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
                if (!RequestModelWithTimeout(fallback, timeoutMs))
                {
                    return new StreamSpawnResult(
                        success: false,
                        usedFallback: usedFallback,
                        resolvedModelName: fallback,
                        vehicle: null,
                        errorMessage: $"Both preferred model '{preferredAddonModel}' and vanilla fallback '{fallback}' failed Gate 3 streaming.");
                }
            }

            // Gate 4: Spawn vehicle and strictly verify non-null handle before touching any vehicle properties.
            IVehicleHandle vehicle = Host.SpawnVehicle(resolvedModel, x, y, z, heading);
            Host.ReleaseModelRequest(resolvedModel);

            if (vehicle == null || !vehicle.Exists())
            {
                return new StreamSpawnResult(
                    success: false,
                    usedFallback: usedFallback,
                    resolvedModelName: resolvedModel,
                    vehicle: null,
                    errorMessage: $"Gate 4 Failure: SpawnVehicle returned null or non-existent handle for '{resolvedModel}'.");
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
