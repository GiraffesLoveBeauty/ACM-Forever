package com.giraffeslovebeauty.acmforever;

import org.junit.Test;
import java.util.Arrays;
import java.util.ArrayList;
import static org.junit.Assert.*;

public class NavigationStackTest {
    @Test public void backVisitsTheActualSourcesInOrder(){NavigationStack<String> stack=new NavigationStack<>();stack.push("mine:luogu:scroll=440");stack.push("problem:P1000");assertEquals("problem:P1000",stack.pop());assertEquals("mine:luogu:scroll=440",stack.pop());assertNull(stack.pop());}
    @Test public void recreationKeepsHistoryOrder(){NavigationStack<String> before=new NavigationStack<>();before.push("forum:q=dp:page=3");before.push("member:public-id");NavigationStack<String> after=new NavigationStack<>();after.restore(before.snapshot());assertEquals("member:public-id",after.pop());assertEquals("forum:q=dp:page=3",after.pop());}
    @Test public void historyHasABound(){NavigationStack<Integer> stack=new NavigationStack<>();for(int i=0;i<40;i++)stack.push(i);for(int i=39;i>=8;i--)assertEquals(Integer.valueOf(i),stack.pop());assertTrue(stack.isEmpty());}
    @Test public void snapshotsCannotMutateTheStack(){NavigationStack<String> stack=new NavigationStack<>();stack.push("problems");ArrayList<String> snapshot=stack.snapshot();snapshot.clear();assertEquals("problems",stack.pop());}
    @Test public void accountChangeCanDiscardEveryPreviousPage(){NavigationStack<String> stack=new NavigationStack<>();stack.restore(Arrays.asList("account","mine"));stack.clear();assertNull(stack.pop());stack.push(null);assertTrue(stack.isEmpty());}
}
