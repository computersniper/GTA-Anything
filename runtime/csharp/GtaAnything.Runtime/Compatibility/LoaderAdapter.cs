using System;
using System.Collections.Generic;

namespace GtaAnything.Runtime.Compatibility
{
    /// <summary>
    /// Clean-room abstraction over a world entity handle (Vehicle, Ped, Blip, Camera, Prop).
    /// Allows GtaAnything.Runtime and transpiled mods to compile and run unit tests without
    /// bundling proprietary game binaries.
    /// </summary>
    public interface IWorldEntityHandle
    {
        int HandleId { get; }
        string ModelName { get; }
        bool Exists();
        void Delete();
        void MarkAsNoLongerNeeded();
    }

    public interface IVehicleHandle : IWorldEntityHandle
    {
        void Repair();
        void SetDoorsShut(bool instant = false);
        bool IsSeatFree(int seatIndex);
    }

    public interface IPedHandle : IWorldEntityHandle
    {
        void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000);
        void TaskLeaveVehicle(IVehicleHandle vehicle, bool warp = false);
    }

    public interface IBlipHandle : IWorldEntityHandle
    {
        void SetRoute(bool enabled);
        void SetColor(int colorCode);
    }

    /// <summary>
    /// Host bridge contract abstracting ScriptHookVDotNet (v3 / Enhanced) or RAGEPluginHook world calls.
    /// </summary>
    public interface IGtaWorldHost
    {
        bool IsStoryModeOrOnDuty { get; }
        bool RequestModel(string modelName);
        bool HasModelLoaded(string modelName);
        void ReleaseModelRequest(string modelName);
        IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f);
        IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f);
        IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "");
        void ShowNotification(string message);
    }

    /// <summary>
    /// Clean-room in-memory <see cref="IGtaWorldHost"/> implementation for standalone builds,
    /// dry-run lifecycle validation, and automated CI tests.
    /// </summary>
    public sealed class SimulatedGtaWorldHost : IGtaWorldHost
    {
        private int _nextHandleId = 1000;
        private readonly HashSet<string> _loadedModels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _releasedModels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _blockedModels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly List<string> _notifications = new List<string>();

        public bool IsStoryModeOrOnDuty { get; set; } = true;
        public IReadOnlyCollection<string> ReleasedModels => _releasedModels;
        public IReadOnlyList<string> Notifications => _notifications;

        /// <summary>
        /// Simulates an addon model that times out during streaming (to test Gate 3 fallback).
        /// </summary>
        public void SimulateModelStreamTimeout(string modelName)
        {
            if (!string.IsNullOrWhiteSpace(modelName))
            {
                _blockedModels.Add(modelName.Trim());
            }
        }

        public bool RequestModel(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            if (_blockedModels.Contains(modelName.Trim()))
            {
                return false;
            }
            _loadedModels.Add(modelName.Trim());
            return true;
        }

        public bool HasModelLoaded(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            return !_blockedModels.Contains(modelName.Trim()) && _loadedModels.Contains(modelName.Trim());
        }

        public void ReleaseModelRequest(string modelName)
        {
            if (!string.IsNullOrWhiteSpace(modelName))
            {
                string key = modelName.Trim();
                _loadedModels.Remove(key);
                _releasedModels.Add(key);
            }
        }

        public IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f)
        {
            if (!HasModelLoaded(modelName))
            {
                return null;
            }
            return new SimulatedVehicleHandle(++_nextHandleId, modelName);
        }

        public IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f)
        {
            if (!HasModelLoaded(modelName))
            {
                RequestModel(modelName);
            }
            return new SimulatedPedHandle(++_nextHandleId, modelName);
        }

        public IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "")
        {
            return new SimulatedBlipHandle(++_nextHandleId, string.IsNullOrWhiteSpace(label) ? "blip" : label);
        }

        public void ShowNotification(string message)
        {
            if (message != null)
            {
                _notifications.Add(message);
            }
        }

        private abstract class SimulatedEntityBase : IWorldEntityHandle
        {
            private bool _exists = true;
            public int HandleId { get; }
            public string ModelName { get; }

            protected SimulatedEntityBase(int handleId, string modelName)
            {
                HandleId = handleId;
                ModelName = modelName ?? "entity";
            }

            public bool Exists() => _exists;
            public void Delete() => _exists = false;
            public void MarkAsNoLongerNeeded() => _exists = false;
        }

        private sealed class SimulatedVehicleHandle : SimulatedEntityBase, IVehicleHandle
        {
            public SimulatedVehicleHandle(int handleId, string modelName) : base(handleId, modelName) { }
            public void Repair() { }
            public void SetDoorsShut(bool instant = false) { }
            public bool IsSeatFree(int seatIndex) => Exists();
        }

        private sealed class SimulatedPedHandle : SimulatedEntityBase, IPedHandle
        {
            public SimulatedPedHandle(int handleId, string modelName) : base(handleId, modelName) { }
            public void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000) { }
            public void TaskLeaveVehicle(IVehicleHandle vehicle, bool warp = false) { }
        }

        private sealed class SimulatedBlipHandle : SimulatedEntityBase, IBlipHandle
        {
            public SimulatedBlipHandle(int handleId, string modelName) : base(handleId, modelName) { }
            public void SetRoute(bool enabled) { }
            public void SetColor(int colorCode) { }
        }
    }

    /// <summary>
    /// Represents a hotkey chord (activation key + optional modifier) with conflict awareness
    /// for RPH (F4), SHVDN (Insert), Trainers (F3/F8), and LSPDFR (B/N/E/Y).
    /// </summary>
    public sealed class HotkeyChord
    {
        private static readonly HashSet<string> HighConflictSingleKeys = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
        {
            "F4", "Insert", "F3", "F8", "B", "N", "E", "Y"
        };

        public string ActivationKey { get; }
        public string ModifierKey { get; }
        public bool RequiresModifier => !string.IsNullOrWhiteSpace(ModifierKey);

        public HotkeyChord(string activationKey, string modifierKey = null)
        {
            if (string.IsNullOrWhiteSpace(activationKey))
            {
                throw new ArgumentException("ActivationKey must not be empty.", nameof(activationKey));
            }
            ActivationKey = activationKey.Trim();
            ModifierKey = string.IsNullOrWhiteSpace(modifierKey) ? null : modifierKey.Trim();
        }

        public bool IsHighConflictWithoutModifier()
        {
            return !RequiresModifier && HighConflictSingleKeys.Contains(ActivationKey);
        }

        public bool Matches(string keyPressed, bool modifierDown)
        {
            if (string.IsNullOrWhiteSpace(keyPressed))
            {
                return false;
            }
            if (!string.Equals(ActivationKey, keyPressed.Trim(), StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
            if (RequiresModifier && !modifierDown)
            {
                return false;
            }
            return true;
        }

        public override string ToString()
        {
            return RequiresModifier ? $"{ModifierKey}+{ActivationKey}" : ActivationKey;
        }
    }

    /// <summary>
    /// Uniform lifecycle adapter across SHVDN v3, SHVDN Enhanced, and RAGEPluginHook.
    /// Guards activation chords with a Story-Mode / On-Duty state check.
    /// </summary>
    public class LoaderAdapter
    {
        public IGtaWorldHost Host { get; }
        public HotkeyChord ActivationChord { get; }
        public LoaderKind ActiveLoader { get; }
        public bool RequireStoryModeOrOnDuty { get; set; } = true;

        public event Action OnTick;
        public event Action OnAbort;
        public event Action<HotkeyChord> OnActivationChordPressed;

        public LoaderAdapter(
            IGtaWorldHost host,
            HotkeyChord chord,
            LoaderKind loaderKind = LoaderKind.ShvdnEnhanced)
        {
            Host = host ?? throw new ArgumentNullException(nameof(host));
            ActivationChord = chord ?? throw new ArgumentNullException(nameof(chord));
            ActiveLoader = loaderKind;
        }

        public void ProcessTick()
        {
            OnTick?.Invoke();
        }

        public void ProcessKeyDown(string keyName, bool modifierDown = false)
        {
            if (RequireStoryModeOrOnDuty && !Host.IsStoryModeOrOnDuty)
            {
                return;
            }

            if (ActivationChord.Matches(keyName, modifierDown))
            {
                OnActivationChordPressed?.Invoke(ActivationChord);
            }
        }

        public void ProcessAbort()
        {
            OnAbort?.Invoke();
        }
    }
}
