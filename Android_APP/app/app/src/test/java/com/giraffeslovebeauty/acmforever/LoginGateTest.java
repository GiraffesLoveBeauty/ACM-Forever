package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import static org.junit.Assert.*;

public class LoginGateTest {
    @Test public void signedOutUsersOnlyReachLoginAndExistingClosureReceipt() {
        assertTrue(LoginGate.permits(false,true,false,false));
        assertTrue(LoginGate.permits(false,false,true,true));
        assertFalse(LoginGate.permits(false,false,true,false));
        assertFalse(LoginGate.permits(false,false,false,true));
        assertFalse(LoginGate.permits(false,false,false,false));
    }
    @Test public void authenticatedUsersReachNormalPages() {
        assertTrue(LoginGate.permits(true,false,false,false));
        assertTrue(LoginGate.permits(true,false,true,false));
    }
}
