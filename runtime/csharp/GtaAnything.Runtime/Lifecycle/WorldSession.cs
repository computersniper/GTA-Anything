using System;
using System.Collections.Generic;
using GtaAnything.Runtime.Compatibility;

namespace GtaAnything.Runtime.Lifecycle
{
    /// <summary>
    /// Lease-based entity lifecycle registry.
    /// Ensures a mod ONLY cleans up its own leased vehicles, peds, blips, and cameras
    /// during shift teardown or script abort—never performing global world wipes that
    /// would corrupt story missions or coexisting plugins.
    /// </summary>
    public sealed class WorldSession : IDisposable
    {
        private readonly object _syncRoot = new object();
        private readonly List<IWorldEntityHandle> _leasedEntities = new List<IWorldEntityHandle>();
        private readonly HashSet<int> _leasedIds = new HashSet<int>();
        private bool _disposed;

        public IGtaWorldHost Host { get; }

        public int ActiveLeaseCount
        {
            get
            {
                lock (_syncRoot)
                {
                    return _leasedEntities.Count;
                }
            }
        }

        public WorldSession(IGtaWorldHost host = null)
        {
            Host = host;
        }

        public IVehicleHandle LeaseVehicle(IVehicleHandle vehicle)
        {
            RegisterInternal(vehicle);
            return vehicle;
        }

        public IPedHandle LeasePed(IPedHandle ped)
        {
            RegisterInternal(ped);
            return ped;
        }

        public IBlipHandle LeaseBlip(IBlipHandle blip)
        {
            RegisterInternal(blip);
            return blip;
        }

        public IWorldEntityHandle LeaseCamera(IWorldEntityHandle camera)
        {
            RegisterInternal(camera);
            return camera;
        }

        /// <summary>
        /// Releases a single leased entity and removes it from the session registry.
        /// </summary>
        public bool ReleaseEntity(IWorldEntityHandle entity, bool deleteImmediately = true)
        {
            if (entity == null)
            {
                return false;
            }

            lock (_syncRoot)
            {
                if (!_leasedIds.Remove(entity.HandleId))
                {
                    return false;
                }

                _leasedEntities.RemoveAll(e => e.HandleId == entity.HandleId);
            }

            SafeReleaseHandle(entity, deleteImmediately);
            return true;
        }

        /// <summary>
        /// Deterministically deletes or releases every entity leased by this session in reverse
        /// creation order (blips/cameras/passengers first, vehicles last).
        /// Returns the number of handles cleaned up.
        /// </summary>
        public int DisposeAll()
        {
            List<IWorldEntityHandle> snapshot;
            lock (_syncRoot)
            {
                snapshot = new List<IWorldEntityHandle>(_leasedEntities);
                _leasedEntities.Clear();
                _leasedIds.Clear();
            }

            int cleaned = 0;
            for (int i = snapshot.Count - 1; i >= 0; i--)
            {
                IWorldEntityHandle handle = snapshot[i];
                if (handle != null)
                {
                    SafeReleaseHandle(handle, deleteImmediately: true);
                    cleaned++;
                }
            }

            return cleaned;
        }

        public void Dispose()
        {
            if (_disposed)
            {
                return;
            }
            _disposed = true;
            DisposeAll();
        }

        private void RegisterInternal(IWorldEntityHandle entity)
        {
            if (entity == null)
            {
                return;
            }

            lock (_syncRoot)
            {
                if (_leasedIds.Add(entity.HandleId))
                {
                    _leasedEntities.Add(entity);
                }
            }
        }

        private static void SafeReleaseHandle(IWorldEntityHandle entity, bool deleteImmediately)
        {
            try
            {
                if (entity.Exists())
                {
                    if (deleteImmediately)
                    {
                        entity.Delete();
                    }
                    else
                    {
                        entity.MarkAsNoLongerNeeded();
                    }
                }
            }
            catch
            {
                // Suppress native teardown exceptions during script abort so remaining leases are still released.
            }
        }
    }
}
