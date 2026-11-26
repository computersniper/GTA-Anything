using System;
using System.Collections.Generic;
using System.Globalization;

namespace GtaAnything.Runtime.Lifecycle
{
    /// <summary>
    /// Canonical operational lifecycle phases aligned with the Gameplay IR specification.
    /// </summary>
    public enum OperationalPhase
    {
        Idle = 0,
        MenuSelecting = 1,
        ResourceStreaming = 2,
        SpawningShift = 3,
        ActiveOperation = 4,
        Completing = 5,
        Teardown = 6
    }

    /// <summary>
    /// Deterministic finite state machine for full operational gameplay loops.
    /// Guarantees that any unhandled exception during tick or transition immediately transitions
    /// to the <see cref="CleanupState"/> ("Teardown") and invokes the registered teardown callback.
    /// </summary>
    public sealed class OperationalStateMachine
    {
        private readonly Dictionary<string, OperationalPhase> _statePhases =
            new Dictionary<string, OperationalPhase>(StringComparer.OrdinalIgnoreCase);

        private readonly Dictionary<string, Dictionary<string, string>> _transitions =
            new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);

        private readonly Action _onTeardownCallback;
        private readonly string _initialState;
        private readonly string _cleanupState;

        public string InitialState { get { return _initialState; } }
        public string CleanupState { get { return _cleanupState; } }
        public string CurrentState { get; private set; }
        public string LastTrigger { get; private set; }

        public OperationalPhase CurrentPhase
        {
            get
            {
                OperationalPhase phase;
                return _statePhases.TryGetValue(CurrentState, out phase)
                    ? phase
                    : OperationalPhase.Idle;
            }
        }

        public event Action<string, string, string> OnStateTransitioned;

        public OperationalStateMachine(
            string initialState = "Idle",
            string cleanupState = "Teardown",
            Action onTeardownCallback = null)
        {
            _initialState = string.IsNullOrWhiteSpace(initialState) ? "Idle" : initialState.Trim();
            _cleanupState = string.IsNullOrWhiteSpace(cleanupState) ? "Teardown" : cleanupState.Trim();
            CurrentState = _initialState;
            _onTeardownCallback = onTeardownCallback;

            // Pre-register canonical states
            RegisterState(_initialState, OperationalPhase.Idle);
            RegisterState("MenuSelecting", OperationalPhase.MenuSelecting);
            RegisterState("ResourceStreaming", OperationalPhase.ResourceStreaming);
            RegisterState("SpawningShift", OperationalPhase.SpawningShift);
            RegisterState("ActiveRoute", OperationalPhase.ActiveOperation);
            RegisterState("ActiveOperation", OperationalPhase.ActiveOperation);
            RegisterState("ShiftSummary", OperationalPhase.Completing);
            RegisterState("Completing", OperationalPhase.Completing);
            RegisterState(_cleanupState, OperationalPhase.Teardown);
        }

        public void RegisterState(string stateName, OperationalPhase phase)
        {
            if (string.IsNullOrWhiteSpace(stateName))
            {
                throw new ArgumentException("State name cannot be empty.", "stateName");
            }
            _statePhases[stateName.Trim()] = phase;
        }

        public void RegisterTransition(string fromState, string toState, string trigger)
        {
            if (string.IsNullOrWhiteSpace(fromState) ||
                string.IsNullOrWhiteSpace(toState) ||
                string.IsNullOrWhiteSpace(trigger))
            {
                throw new ArgumentException("Transition states and trigger must be non-empty.");
            }

            string fromKey = fromState.Trim();
            string toKey = toState.Trim();
            string triggerKey = trigger.Trim();

            Dictionary<string, string> edges;
            if (!_transitions.TryGetValue(fromKey, out edges))
            {
                edges = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                _transitions[fromKey] = edges;
            }

            edges[triggerKey] = toKey;
        }

        /// <summary>
        /// Attempts to fire a transition trigger from the current state.
        /// If transitioning into <see cref="CleanupState"/>, invokes the teardown callback.
        /// </summary>
        public bool TryFire(string trigger, out string nextState)
        {
            nextState = CurrentState;
            if (string.IsNullOrWhiteSpace(trigger))
            {
                return false;
            }

            Dictionary<string, string> edges;
            string target;
            if (!_transitions.TryGetValue(CurrentState, out edges) ||
                !edges.TryGetValue(trigger.Trim(), out target))
            {
                return false;
            }

            string previous = CurrentState;
            CurrentState = target;
            LastTrigger = trigger.Trim();
            nextState = CurrentState;

            if (string.Equals(CurrentState, _cleanupState, StringComparison.OrdinalIgnoreCase))
            {
                if (_onTeardownCallback != null)
                {
                    _onTeardownCallback();
                }
            }

            Action<string, string, string> handler = OnStateTransitioned;
            if (handler != null)
            {
                handler(previous, CurrentState, LastTrigger);
            }
            return true;
        }

        /// <summary>
        /// Fires the trigger if valid; otherwise forces an emergency transition to <see cref="CleanupState"/>.
        /// </summary>
        public void FireOrTeardown(string trigger)
        {
            string ignored;
            if (!TryFire(trigger, out ignored))
            {
                ForceTeardown(string.Format(CultureInfo.InvariantCulture, "InvalidTrigger:{0}", trigger));
            }
        }

        /// <summary>
        /// Executes an operational step inside a fault barrier. If an unhandled exception occurs,
        /// immediately transitions to <see cref="CleanupState"/> so leased entities are released.
        /// </summary>
        public void ExecuteGuarded(Action action, Action<Exception> onError = null)
        {
            if (action == null)
            {
                return;
            }

            try
            {
                action();
            }
            catch (Exception ex)
            {
                if (onError != null)
                {
                    onError(ex);
                }
                ForceTeardown(string.Format(CultureInfo.InvariantCulture, "UnhandledException:{0}", ex.GetType().Name));
            }
        }

        /// <summary>
        /// Forces an immediate transition to <see cref="CleanupState"/> and invokes teardown cleanup.
        /// </summary>
        public void ForceTeardown(string reason = "Forced")
        {
            string previous = CurrentState;
            CurrentState = _cleanupState;
            LastTrigger = reason ?? "Forced";
            if (_onTeardownCallback != null)
            {
                _onTeardownCallback();
            }
            Action<string, string, string> handler = OnStateTransitioned;
            if (handler != null)
            {
                handler(previous, CurrentState, LastTrigger);
            }
        }
    }
}
