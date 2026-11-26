using System;

namespace GtaAnything.Runtime.Compatibility
{
    /// <summary>
    /// Clean-room factory selecting the compiled native host bridge (<see cref="IGtaWorldHost"/>)
    /// when SHVDN or RPH SDK assemblies are referenced, or falling back to
    /// <see cref="SimulatedGtaWorldHost"/> for standalone netstandard2.0 builds and offline CI.
    /// </summary>
    public static class HostBridgeFactory
    {
        public static string ActiveBridgeName
        {
            get
            {
#if RPH_REFERENCED
                return "RphWorldHostBridge";
#elif SHVDN_REFERENCED
                return "ShvdnWorldHostBridge";
#else
                return "SimulatedGtaWorldHost";
#endif
            }
        }

        public static IGtaWorldHost CreateDefaultHost(LoaderKind? preferredLoader = null)
        {
#if RPH_REFERENCED
            if (!preferredLoader.HasValue || preferredLoader.Value == LoaderKind.RagePluginHook)
            {
                return new RphWorldHostBridge();
            }
#endif
#if SHVDN_REFERENCED
            if (!preferredLoader.HasValue ||
                preferredLoader.Value == LoaderKind.ShvdnV3 ||
                preferredLoader.Value == LoaderKind.ShvdnEnhanced)
            {
                return new ShvdnWorldHostBridge();
            }
#endif
            return new SimulatedGtaWorldHost();
        }
    }

#if SHVDN_REFERENCED
    /// <summary>
    /// Clean-room ScriptHookVDotNet (v3 / Enhanced) host bridge implementing <see cref="IGtaWorldHost"/>.
    /// Compiled only when <c>SHVDN_REFERENCED</c> is defined alongside a user-supplied SHVDN reference.
    /// </summary>
    public sealed class ShvdnWorldHostBridge : IGtaWorldHost
    {
        public bool IsStoryModeOrOnDuty
        {
            get
            {
                return GTA.Game.Player != null &&
                       GTA.Game.Player.Character != null &&
                       GTA.Game.Player.Character.Exists();
            }
        }

        public bool RequestModel(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            GTA.Model model = new GTA.Model(modelName.Trim());
            if (!model.IsValid)
            {
                return false;
            }
            model.Request();
            return model.IsLoaded;
        }

        public bool HasModelLoaded(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            GTA.Model model = new GTA.Model(modelName.Trim());
            return model.IsValid && model.IsLoaded;
        }

        public void ReleaseModelRequest(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return;
            }
            GTA.Model model = new GTA.Model(modelName.Trim());
            if (model.IsValid)
            {
                model.MarkAsNoLongerNeeded();
            }
        }

        public IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f)
        {
            GTA.Model model = new GTA.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            GTA.Vehicle vehicle = GTA.World.CreateVehicle(model, new GTA.Math.Vector3(x, y, z), heading);
            return vehicle == null ? null : new ShvdnVehicleHandle(vehicle, modelName);
        }

        public IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f)
        {
            GTA.Model model = new GTA.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            GTA.Ped ped = GTA.World.CreatePed(model, new GTA.Math.Vector3(x, y, z), heading);
            return ped == null ? null : new ShvdnPedHandle(ped, modelName);
        }

        public IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "")
        {
            GTA.Blip blip = GTA.World.CreateBlip(new GTA.Math.Vector3(x, y, z));
            if (blip == null)
            {
                return null;
            }
            blip.Sprite = (GTA.BlipSprite)sprite;
            blip.Color = (GTA.BlipColor)color;
            if (!string.IsNullOrWhiteSpace(label))
            {
                blip.Name = label;
            }
            return new ShvdnBlipHandle(blip, string.IsNullOrWhiteSpace(label) ? "blip" : label);
        }

        public void ShowNotification(string message)
        {
            if (!string.IsNullOrWhiteSpace(message))
            {
                GTA.UI.Notification.PostTicker(message, true, true);
            }
        }

        public void ShowSubtitle(string message, int durationMs = 2500)
        {
            if (!string.IsNullOrWhiteSpace(message))
            {
                GTA.UI.Screen.ShowSubtitle(message, durationMs);
            }
        }

        public bool SeatPlayerInVehicle(IVehicleHandle vehicle, int seatIndex = -1)
        {
            ShvdnVehicleHandle veh = vehicle as ShvdnVehicleHandle;
            if (veh == null || !veh.Exists())
            {
                return false;
            }
            if (GTA.Game.Player == null || GTA.Game.Player.Character == null)
            {
                return false;
            }
            GTA.Game.Player.Character.SetIntoVehicle(veh.Inner, (GTA.VehicleSeat)seatIndex);
            return true;
        }

        public float GetPlayerDistanceTo(float x, float y, float z)
        {
            if (GTA.Game.Player == null || GTA.Game.Player.Character == null)
            {
                return float.MaxValue;
            }
            return GTA.Game.Player.Character.Position.DistanceTo(new GTA.Math.Vector3(x, y, z));
        }

        public float GetPlayerSpeed()
        {
            if (GTA.Game.Player == null || GTA.Game.Player.Character == null)
            {
                return 0f;
            }
            GTA.Ped playerPed = GTA.Game.Player.Character;
            if (playerPed.CurrentVehicle != null && playerPed.CurrentVehicle.Exists())
            {
                return playerPed.CurrentVehicle.Speed;
            }
            return playerPed.Speed;
        }

        public void DrawCheckpointMarker(float x, float y, float z, float radius = 4.0f)
        {
            GTA.World.DrawMarker(
                GTA.MarkerType.Cylinder,
                new GTA.Math.Vector3(x, y, z - 1.0f),
                GTA.Math.Vector3.Zero,
                GTA.Math.Vector3.Zero,
                new GTA.Math.Vector3(radius, radius, 1.5f),
                System.Drawing.Color.FromArgb(140, 0, 200, 255),
                false,
                false,
                false,
                null,
                null,
                false);
        }

        private sealed class ShvdnVehicleHandle : IVehicleHandle
        {
            private readonly GTA.Vehicle _inner;
            private readonly string _modelName;

            internal GTA.Vehicle Inner { get { return _inner; } }
            public int HandleId { get { return _inner.Handle; } }
            public string ModelName { get { return _modelName; } }

            public ShvdnVehicleHandle(GTA.Vehicle vehicle, string modelName)
            {
                _inner = vehicle;
                _modelName = modelName ?? "vehicle";
            }

            public bool Exists() { return _inner != null && _inner.Exists(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { if (Exists()) { _inner.MarkAsNoLongerNeeded(); } }
            public void Repair() { if (Exists()) { _inner.Repair(); } }

            public void SetDoorsShut(bool instant = false)
            {
                if (!Exists() || _inner.Doors == null)
                {
                    return;
                }
                GTA.VehicleDoor[] doors = _inner.Doors.ToArray();
                if (doors == null)
                {
                    return;
                }
                for (int i = 0; i < doors.Length; i++)
                {
                    if (doors[i] != null)
                    {
                        doors[i].Close(instant);
                    }
                }
            }

            public bool IsSeatFree(int seatIndex)
            {
                return Exists() && _inner.IsSeatFree((GTA.VehicleSeat)seatIndex);
            }
        }

        private sealed class ShvdnPedHandle : IPedHandle
        {
            private readonly GTA.Ped _inner;
            private readonly string _modelName;

            public int HandleId { get { return _inner.Handle; } }
            public string ModelName { get { return _modelName; } }

            public ShvdnPedHandle(GTA.Ped ped, string modelName)
            {
                _inner = ped;
                _modelName = modelName ?? "ped";
            }

            public bool Exists() { return _inner != null && _inner.Exists(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { if (Exists()) { _inner.MarkAsNoLongerNeeded(); } }

            public void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000)
            {
                ShvdnVehicleHandle veh = vehicle as ShvdnVehicleHandle;
                if (Exists() && veh != null && veh.Exists())
                {
                    _inner.Task.EnterVehicle(
                        veh.Inner,
                        (GTA.VehicleSeat)seatIndex,
                        timeoutMs,
                        1.0f,
                        (GTA.EnterVehicleFlags)0);
                }
            }

            public void TaskLeaveVehicle(IVehicleHandle vehicle, bool warp = false)
            {
                if (Exists())
                {
                    _inner.Task.LeaveVehicle(warp ? GTA.LeaveVehicleFlags.WarpOut : GTA.LeaveVehicleFlags.None);
                }
            }
        }

        private sealed class ShvdnBlipHandle : IBlipHandle
        {
            private readonly GTA.Blip _inner;
            private readonly string _modelName;

            public int HandleId { get { return _inner.Handle; } }
            public string ModelName { get { return _modelName; } }

            public ShvdnBlipHandle(GTA.Blip blip, string label)
            {
                _inner = blip;
                _modelName = label ?? "blip";
            }

            public bool Exists() { return _inner != null && _inner.Exists(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { Delete(); }
            public void SetRoute(bool enabled) { if (Exists()) { _inner.ShowRoute = enabled; } }
            public void SetColor(int colorCode) { if (Exists()) { _inner.Color = (GTA.BlipColor)colorCode; } }
        }
    }
#endif

#if RPH_REFERENCED
    /// <summary>
    /// Clean-room RAGE Plugin Hook (RPH) host bridge implementing <see cref="IGtaWorldHost"/>.
    /// Compiled only when <c>RPH_REFERENCED</c> is defined alongside a user-supplied RPH SDK reference.
    /// </summary>
    public sealed class RphWorldHostBridge : IGtaWorldHost
    {
        public bool IsStoryModeOrOnDuty
        {
            get
            {
                return !Rage.Game.IsLoading &&
                       Rage.Game.LocalPlayer != null &&
                       Rage.Game.LocalPlayer.Character != null;
            }
        }

        public bool RequestModel(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            Rage.Model model = new Rage.Model(modelName.Trim());
            if (!model.IsValid)
            {
                return false;
            }
            model.Load();
            return model.IsLoaded;
        }

        public bool HasModelLoaded(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            Rage.Model model = new Rage.Model(modelName.Trim());
            return model.IsValid && model.IsLoaded;
        }

        public void ReleaseModelRequest(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return;
            }
            Rage.Model model = new Rage.Model(modelName.Trim());
            if (model.IsValid && model.IsLoaded)
            {
                model.Dismiss();
            }
        }

        public IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f)
        {
            Rage.Model model = new Rage.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            Rage.Vehicle vehicle = new Rage.Vehicle(model, new Rage.Vector3(x, y, z), heading);
            return vehicle.IsValid() ? new RphVehicleHandle(vehicle, modelName) : null;
        }

        public IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f)
        {
            Rage.Model model = new Rage.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            Rage.Ped ped = new Rage.Ped(model, new Rage.Vector3(x, y, z), heading);
            return ped.IsValid() ? new RphPedHandle(ped, modelName) : null;
        }

        public IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "")
        {
            Rage.Blip blip = new Rage.Blip(new Rage.Vector3(x, y, z));
            if (!blip.IsValid())
            {
                return null;
            }
            blip.Sprite = (Rage.BlipSprite)sprite;
            if (!string.IsNullOrWhiteSpace(label))
            {
                blip.Name = label;
            }
            return new RphBlipHandle(blip, string.IsNullOrWhiteSpace(label) ? "blip" : label);
        }

        public void ShowNotification(string message)
        {
            if (!string.IsNullOrWhiteSpace(message))
            {
                Rage.Game.DisplayNotification(message);
            }
        }

        public void ShowSubtitle(string message, int durationMs = 2500)
        {
            if (!string.IsNullOrWhiteSpace(message))
            {
                Rage.Game.DisplaySubtitle(message, durationMs);
            }
        }

        public bool SeatPlayerInVehicle(IVehicleHandle vehicle, int seatIndex = -1)
        {
            RphVehicleHandle veh = vehicle as RphVehicleHandle;
            if (veh == null || !veh.Exists() || Rage.Game.LocalPlayer == null || Rage.Game.LocalPlayer.Character == null)
            {
                return false;
            }
            Rage.Game.LocalPlayer.Character.WarpIntoVehicle(veh.Inner, seatIndex);
            return true;
        }

        public float GetPlayerDistanceTo(float x, float y, float z)
        {
            if (Rage.Game.LocalPlayer == null || Rage.Game.LocalPlayer.Character == null)
            {
                return float.MaxValue;
            }
            return Rage.Game.LocalPlayer.Character.Position.DistanceTo(new Rage.Vector3(x, y, z));
        }

        public float GetPlayerSpeed()
        {
            if (Rage.Game.LocalPlayer == null || Rage.Game.LocalPlayer.Character == null)
            {
                return 0f;
            }
            return Rage.Game.LocalPlayer.Character.Speed;
        }

        public void DrawCheckpointMarker(float x, float y, float z, float radius = 4.0f)
        {
        }

        private sealed class RphVehicleHandle : IVehicleHandle
        {
            private readonly Rage.Vehicle _inner;
            private readonly string _modelName;

            internal Rage.Vehicle Inner { get { return _inner; } }
            public int HandleId { get { return (int)_inner.Handle.Value; } }
            public string ModelName { get { return _modelName; } }

            public RphVehicleHandle(Rage.Vehicle vehicle, string modelName)
            {
                _inner = vehicle;
                _modelName = modelName ?? "vehicle";
            }

            public bool Exists() { return _inner != null && _inner.IsValid(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { if (Exists()) { _inner.Dismiss(); } }
            public void Repair() { if (Exists()) { _inner.Repair(); } }
            public void SetDoorsShut(bool instant = false) { }
            public bool IsSeatFree(int seatIndex) { return Exists() && _inner.IsSeatFree(seatIndex); }
        }

        private sealed class RphPedHandle : IPedHandle
        {
            private readonly Rage.Ped _inner;
            private readonly string _modelName;

            public int HandleId { get { return (int)_inner.Handle.Value; } }
            public string ModelName { get { return _modelName; } }

            public RphPedHandle(Rage.Ped ped, string modelName)
            {
                _inner = ped;
                _modelName = modelName ?? "ped";
            }

            public bool Exists() { return _inner != null && _inner.IsValid(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { if (Exists()) { _inner.Dismiss(); } }

            public void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000)
            {
                RphVehicleHandle veh = vehicle as RphVehicleHandle;
                if (Exists() && veh != null && veh.Exists())
                {
                    _inner.Tasks.EnterVehicle(veh.Inner, timeoutMs, seatIndex);
                }
            }

            public void TaskLeaveVehicle(IVehicleHandle vehicle, bool warp = false)
            {
                if (Exists())
                {
                    _inner.Tasks.LeaveVehicle(warp ? Rage.LeaveVehicleFlags.WarpOut : Rage.LeaveVehicleFlags.None);
                }
            }
        }

        private sealed class RphBlipHandle : IBlipHandle
        {
            private readonly Rage.Blip _inner;
            private readonly string _modelName;

            public int HandleId { get { return (int)_inner.Handle.Value; } }
            public string ModelName { get { return _modelName; } }

            public RphBlipHandle(Rage.Blip blip, string label)
            {
                _inner = blip;
                _modelName = label ?? "blip";
            }

            public bool Exists() { return _inner != null && _inner.IsValid(); }
            public void Delete() { if (Exists()) { _inner.Delete(); } }
            public void MarkAsNoLongerNeeded() { Delete(); }
            public void SetRoute(bool enabled) { if (Exists()) { _inner.IsRouteEnabled = enabled; } }
            public void SetColor(int colorCode) { }
        }
    }
#endif
}
