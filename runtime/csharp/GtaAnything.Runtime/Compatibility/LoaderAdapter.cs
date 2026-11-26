using System;
using System.Collections.Generic;
using System.Globalization;

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
        void ShowSubtitle(string message, int durationMs = 2500);
        bool SeatPlayerInVehicle(IVehicleHandle vehicle, int seatIndex = -1);
        float GetPlayerDistanceTo(float x, float y, float z);
        float GetPlayerSpeed();
        void DrawCheckpointMarker(float x, float y, float z, float radius = 4.0f);
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
        private readonly List<string> _subtitles = new List<string>();
        private bool _isStoryModeOrOnDuty = true;

        public bool IsStoryModeOrOnDuty
        {
            get { return _isStoryModeOrOnDuty; }
            set { _isStoryModeOrOnDuty = value; }
        }

        public IReadOnlyCollection<string> ReleasedModels { get { return _releasedModels; } }
        public IReadOnlyList<string> Notifications { get { return _notifications; } }
        public IReadOnlyList<string> Subtitles { get { return _subtitles; } }

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
            string trimmed = modelName.Trim();
            if (_blockedModels.Contains(trimmed))
            {
                return false;
            }
            _loadedModels.Add(trimmed);
            return true;
        }

        public bool HasModelLoaded(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            string trimmed = modelName.Trim();
            return !_blockedModels.Contains(trimmed) && _loadedModels.Contains(trimmed);
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

        public void ShowSubtitle(string message, int durationMs = 2500)
        {
            if (message != null)
            {
                _subtitles.Add(message);
            }
        }

        public bool SeatPlayerInVehicle(IVehicleHandle vehicle, int seatIndex = -1)
        {
            return vehicle != null && vehicle.Exists();
        }

        public float GetPlayerDistanceTo(float x, float y, float z)
        {
            return 0f;
        }

        public float GetPlayerSpeed()
        {
            return 0f;
        }

        public void DrawCheckpointMarker(float x, float y, float z, float radius = 4.0f)
        {
        }

        private abstract class SimulatedEntityBase : IWorldEntityHandle
        {
            private bool _exists = true;
            private readonly int _handleId;
            private readonly string _modelName;

            public int HandleId { get { return _handleId; } }
            public string ModelName { get { return _modelName; } }

            protected SimulatedEntityBase(int handleId, string modelName)
            {
                _handleId = handleId;
                _modelName = modelName ?? "entity";
            }

            public bool Exists() { return _exists; }
            public void Delete() { _exists = false; }
            public void MarkAsNoLongerNeeded() { _exists = false; }
        }

        private sealed class SimulatedVehicleHandle : SimulatedEntityBase, IVehicleHandle
        {
            public SimulatedVehicleHandle(int handleId, string modelName) : base(handleId, modelName) { }
            public void Repair() { }
            public void SetDoorsShut(bool instant = false) { }
            public bool IsSeatFree(int seatIndex) { return Exists(); }
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

        private readonly string _activationKey;
        private readonly string _modifierKey;

        public string ActivationKey { get { return _activationKey; } }
        public string ModifierKey { get { return _modifierKey; } }
        public bool RequiresModifier { get { return !string.IsNullOrWhiteSpace(_modifierKey); } }

        public HotkeyChord(string activationKey, string modifierKey = null)
        {
            if (string.IsNullOrWhiteSpace(activationKey))
            {
                throw new ArgumentException("ActivationKey must not be empty.", "activationKey");
            }
            _activationKey = activationKey.Trim();
            _modifierKey = string.IsNullOrWhiteSpace(modifierKey) ? null : modifierKey.Trim();
        }

        public bool IsHighConflictWithoutModifier()
        {
            return !RequiresModifier && HighConflictSingleKeys.Contains(_activationKey);
        }

        public bool Matches(string keyPressed, bool modifierDown)
        {
            if (string.IsNullOrWhiteSpace(keyPressed))
            {
                return false;
            }
            if (!string.Equals(_activationKey, keyPressed.Trim(), StringComparison.OrdinalIgnoreCase))
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
            return RequiresModifier
                ? string.Format(CultureInfo.InvariantCulture, "{0}+{1}", _modifierKey, _activationKey)
                : _activationKey;
        }
    }

    /// <summary>
    /// Uniform lifecycle adapter across SHVDN v3, SHVDN Enhanced, and RAGEPluginHook.
    /// Guards activation chords with a Story-Mode / On-Duty state check.
    /// </summary>
    public class LoaderAdapter
    {
        private readonly IGtaWorldHost _host;
        private readonly HotkeyChord _activationChord;
        private readonly LoaderKind _activeLoader;
        private bool _requireStoryModeOrOnDuty = true;

        public IGtaWorldHost Host { get { return _host; } }
        public HotkeyChord ActivationChord { get { return _activationChord; } }
        public LoaderKind ActiveLoader { get { return _activeLoader; } }

        public bool RequireStoryModeOrOnDuty
        {
            get { return _requireStoryModeOrOnDuty; }
            set { _requireStoryModeOrOnDuty = value; }
        }

        public event Action OnTick;
        public event Action OnAbort;
        public event Action<HotkeyChord> OnActivationChordPressed;

        public LoaderAdapter(
            IGtaWorldHost host,
            HotkeyChord chord,
            LoaderKind loaderKind = LoaderKind.ShvdnEnhanced)
        {
            if (host == null)
            {
                throw new ArgumentNullException("host");
            }
            if (chord == null)
            {
                throw new ArgumentNullException("chord");
            }
            _host = host;
            _activationChord = chord;
            _activeLoader = loaderKind;
        }

        public void ProcessTick()
        {
            Action handler = OnTick;
            if (handler != null)
            {
                handler();
            }
        }

        public void ProcessKeyDown(string keyName, bool modifierDown = false)
        {
            if (RequireStoryModeOrOnDuty && !_host.IsStoryModeOrOnDuty)
            {
                return;
            }

            if (_activationChord.Matches(keyName, modifierDown))
            {
                Action<HotkeyChord> handler = OnActivationChordPressed;
                if (handler != null)
                {
                    handler(_activationChord);
                }
            }
        }

        public void ProcessAbort()
        {
            Action handler = OnAbort;
            if (handler != null)
            {
                handler();
            }
        }
    }
}
