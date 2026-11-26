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
                return nameof(RphWorldHostBridge);
#elif SHVDN_REFERENCED
                return nameof(ShvdnWorldHostBridge);
#else
                return nameof(SimulatedGtaWorldHost);
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
        public bool IsStoryModeOrOnDuty => !GTA.Game.IsLoading && GTA.Game.Player?.Character != null;

        public bool RequestModel(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            var model = new GTA.Model(modelName.Trim());
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
            var model = new GTA.Model(modelName.Trim());
            return model.IsValid && model.IsLoaded;
        }

        public void ReleaseModelRequest(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return;
            }
            var model = new GTA.Model(modelName.Trim());
            if (model.IsValid)
            {
                model.MarkAsNoLongerNeeded();
            }
        }

        public IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f)
        {
            var model = new GTA.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            var vehicle = GTA.World.CreateVehicle(model, new GTA.Math.Vector3(x, y, z), heading);
            return vehicle == null ? null : new ShvdnVehicleHandle(vehicle, modelName);
        }

        public IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f)
        {
            var model = new GTA.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            var ped = GTA.World.CreatePed(model, new GTA.Math.Vector3(x, y, z), heading);
            return ped == null ? null : new ShvdnPedHandle(ped, modelName);
        }

        public IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "")
        {
            var blip = GTA.World.CreateBlip(new GTA.Math.Vector3(x, y, z));
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
                GTA.UI.Notification.Show(message);
            }
        }

        private sealed class ShvdnVehicleHandle : IVehicleHandle
        {
            internal GTA.Vehicle Inner { get; }
            public int HandleId => Inner.Handle;
            public string ModelName { get; }

            public ShvdnVehicleHandle(GTA.Vehicle vehicle, string modelName)
            {
                Inner = vehicle;
                ModelName = modelName ?? "vehicle";
            }

            public bool Exists() => Inner != null && Inner.Exists();
            public void Delete() { if (Exists()) Inner.Delete(); }
            public void MarkAsNoLongerNeeded() { if (Exists()) Inner.MarkAsNoLongerNeeded(); }
            public void Repair() { if (Exists()) Inner.Repair(); }
            public void SetDoorsShut(bool instant = false) { if (Exists()) Inner.Doors.CloseAll(instant); }
            public bool IsSeatFree(int seatIndex) => Exists() && Inner.IsSeatFree((GTA.VehicleSeat)seatIndex);
        }

        private sealed class ShvdnPedHandle : IPedHandle
        {
            private readonly GTA.Ped _inner;
            public int HandleId => _inner.Handle;
            public string ModelName { get; }

            public ShvdnPedHandle(GTA.Ped ped, string modelName)
            {
                _inner = ped;
                ModelName = modelName ?? "ped";
            }

            public bool Exists() => _inner != null && _inner.Exists();
            public void Delete() { if (Exists()) _inner.Delete(); }
            public void MarkAsNoLongerNeeded() { if (Exists()) _inner.MarkAsNoLongerNeeded(); }

            public void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000)
            {
                if (Exists() && vehicle is ShvdnVehicleHandle veh && veh.Exists())
                {
                    _inner.Task.EnterVehicle(veh.Inner, (GTA.VehicleSeat)seatIndex, timeoutMs);
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
            public int HandleId => _inner.Handle;
            public string ModelName { get; }

            public ShvdnBlipHandle(GTA.Blip blip, string label)
            {
                _inner = blip;
                ModelName = label ?? "blip";
            }

            public bool Exists() => _inner != null && _inner.Exists();
            public void Delete() { if (Exists()) _inner.Delete(); }
            public void MarkAsNoLongerNeeded() { Delete(); }
            public void SetRoute(bool enabled) { if (Exists()) _inner.ShowRoute = enabled; }
            public void SetColor(int colorCode) { if (Exists()) _inner.Color = (GTA.BlipColor)colorCode; }
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
        public bool IsStoryModeOrOnDuty => !Rage.Game.IsLoading && Rage.Game.LocalPlayer?.Character != null;

        public bool RequestModel(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return false;
            }
            var model = new Rage.Model(modelName.Trim());
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
            var model = new Rage.Model(modelName.Trim());
            return model.IsValid && model.IsLoaded;
        }

        public void ReleaseModelRequest(string modelName)
        {
            if (string.IsNullOrWhiteSpace(modelName))
            {
                return;
            }
            var model = new Rage.Model(modelName.Trim());
            if (model.IsValid && model.IsLoaded)
            {
                model.Dismiss();
            }
        }

        public IVehicleHandle SpawnVehicle(string modelName, float x, float y, float z, float heading = 0f)
        {
            var model = new Rage.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            var vehicle = new Rage.Vehicle(model, new Rage.Vector3(x, y, z), heading);
            return vehicle.IsValid() ? new RphVehicleHandle(vehicle, modelName) : null;
        }

        public IPedHandle SpawnPed(string modelName, float x, float y, float z, float heading = 0f)
        {
            var model = new Rage.Model(modelName);
            if (!model.IsValid || !model.IsLoaded)
            {
                return null;
            }
            var ped = new Rage.Ped(model, new Rage.Vector3(x, y, z), heading);
            return ped.IsValid() ? new RphPedHandle(ped, modelName) : null;
        }

        public IBlipHandle CreateBlip(float x, float y, float z, int sprite = 1, int color = 3, string label = "")
        {
            var blip = new Rage.Blip(new Rage.Vector3(x, y, z));
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

        private sealed class RphVehicleHandle : IVehicleHandle
        {
            internal Rage.Vehicle Inner { get; }
            public int HandleId => (int)Inner.Handle.Value;
            public string ModelName { get; }

            public RphVehicleHandle(Rage.Vehicle vehicle, string modelName)
            {
                Inner = vehicle;
                ModelName = modelName ?? "vehicle";
            }

            public bool Exists() => Inner != null && Inner.IsValid();
            public void Delete() { if (Exists()) Inner.Delete(); }
            public void MarkAsNoLongerNeeded() { if (Exists()) Inner.Dismiss(); }
            public void Repair() { if (Exists()) Inner.Repair(); }
            public void SetDoorsShut(bool instant = false) { }
            public bool IsSeatFree(int seatIndex) => Exists() && Inner.IsSeatFree(seatIndex);
        }

        private sealed class RphPedHandle : IPedHandle
        {
            private readonly Rage.Ped _inner;
            public int HandleId => (int)_inner.Handle.Value;
            public string ModelName { get; }

            public RphPedHandle(Rage.Ped ped, string modelName)
            {
                _inner = ped;
                ModelName = modelName ?? "ped";
            }

            public bool Exists() => _inner != null && _inner.IsValid();
            public void Delete() { if (Exists()) _inner.Delete(); }
            public void MarkAsNoLongerNeeded() { if (Exists()) _inner.Dismiss(); }

            public void TaskEnterVehicle(IVehicleHandle vehicle, int seatIndex, int timeoutMs = 5000)
            {
                if (Exists() && vehicle is RphVehicleHandle veh && veh.Exists())
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
            public int HandleId => (int)_inner.Handle.Value;
            public string ModelName { get; }

            public RphBlipHandle(Rage.Blip blip, string label)
            {
                _inner = blip;
                ModelName = label ?? "blip";
            }

            public bool Exists() => _inner != null && _inner.IsValid();
            public void Delete() { if (Exists()) _inner.Delete(); }
            public void MarkAsNoLongerNeeded() { Delete(); }
            public void SetRoute(bool enabled) { if (Exists()) _inner.IsRouteEnabled = enabled; }
            public void SetColor(int colorCode) { }
        }
    }
#endif
}
